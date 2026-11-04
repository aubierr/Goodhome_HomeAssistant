"""Client Bluetooth local d'un radiateur GoodHome.

Même interface que le client cloud (async_get_devices, async_set_state, async_identify) :
le coordinator et les entités fonctionnent de la même façon dans les deux modes.
Le Bluetooth de Home Assistant n'est importé qu'ici, pour ne pas l'imposer au mode cloud.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant, callback

from .ble import (
    LOCAL_NAME_PREFIX,
    NOTIFY_UUID,
    SERVICE_UUID,
    TYPE_DATA,
    TYPE_NACK,
    WRITE_UUID,
    FrameDecoder,
    attributes_in,
    build_ack,
    build_frame,
    build_get_attr,
    build_set_attr,
    build_system_command,
    from_radiator,
    split_chunks,
    complete_mode_change,
)
from .goodhome_api import GoodHomeError

_LOGGER = logging.getLogger(__name__)

COMMAND_TIMEOUT = 10  # Attente de la réponse « return » à une commande (secondes)
ATTRIBUTES_TIMEOUT = 10  # Attente des attributs après getAttr (secondes)
ATTRIBUTES_QUIET = 1.5  # Les attributs arrivent en plusieurs messages : fin après ce silence
CHUNK_DELAY = 0.05  # Pause entre deux morceaux écrits, comme l'appli


class GoodHomeBleError(GoodHomeError):
    """Radiateur injoignable en Bluetooth ou réponse inattendue."""


class GoodHomeBleNotFound(GoodHomeBleError):
    """Radiateur absent des annonces Bluetooth récentes (éteint ou trop loin)."""


class GoodHomeBlePairingRejected(GoodHomeBleError):
    """Appairage refusé : le radiateur n'était pas en mode appairage."""


# Erreurs BlueZ d'un appairage refusé, et d'une ancienne clé que le radiateur n'a plus
REJECTED_ERRORS = ("AuthenticationCanceled", "AuthenticationRejected", "AuthenticationFailed", "Error.Rejected")
STALE_KEY_ERRORS = ("key-missing", "Unlikely Error", "UNLIKELY_ERROR")
DEVICE_WAIT = 20  # Attente d'une annonce récente du radiateur (secondes)
FRESH_ADVERTISEMENT = 10  # Âge maximal d'une annonce pour s'y connecter (secondes)
CONNECT_WAIT = 30  # Attente d'une annonce avant chaque connexion (secondes)
PROXY_PAIRING_ATTEMPTS = 3  # Envois de la première demande après un appairage via un proxy (×10 s)


@callback
def async_connectable_scanner_count(hass: HomeAssistant) -> int:
    """Nombre d'adaptateurs ou de proxys Bluetooth capables de se connecter (0 sans Bluetooth chargé)."""
    from homeassistant.components import bluetooth

    try:
        return bluetooth.async_scanner_count(hass, connectable=True)
    except Exception as err:  # noqa: BLE001 - Bluetooth de Home Assistant pas encore chargé
        _LOGGER.debug("Cannot count Bluetooth scanners: %s", err)
        return 0


@callback
def async_rediscover(hass: HomeAssistant, *addresses: str) -> None:
    """Oublier les découvertes passées de ces adresses, pour que la carte « Découvertes » revienne."""
    from homeassistant.components import bluetooth

    for address in dict.fromkeys(address for address in addresses if address):
        try:
            bluetooth.async_rediscover_address(hass, address)
        except Exception as err:  # noqa: BLE001 - redécouverte au mieux, la suppression continue
            _LOGGER.debug("Cannot rediscover Bluetooth address %s: %s", address, err)


@callback
def async_request_active_scan(hass: HomeAssistant) -> None:
    """Demander une recherche active en tâche de fond (Home Assistant récent seulement).

    Un radiateur lointain n'est entendu que de temps en temps en recherche passive : une
    recherche active fait arriver ses annonces plus vite.
    """
    from homeassistant.components import bluetooth

    request = getattr(bluetooth, "async_request_active_scan", None)
    if request is None:
        return

    async def _async_scan() -> None:
        try:
            await request(hass)
        except Exception as err:  # noqa: BLE001 - recherche en plus, au mieux
            _LOGGER.debug("Active Bluetooth scan failed: %s", err)

    hass.async_create_background_task(_async_scan(), "goodhome ble active scan")


@callback
def async_reachability(hass: HomeAssistant, address: str) -> str | None:
    """Explication lisible de Home Assistant sur la joignabilité d'une adresse (récent seulement)."""
    from homeassistant.components import bluetooth

    diagnose = getattr(bluetooth, "async_address_reachability_diagnostics", None)
    intent = getattr(getattr(bluetooth, "BluetoothReachabilityIntent", None), "CONNECTION", None)
    if diagnose is None or intent is None:
        return None
    try:
        return diagnose(hass, address, intent) or None
    except Exception as err:  # noqa: BLE001 - explication en plus, au mieux
        _LOGGER.debug("Bluetooth reachability diagnostics of %s failed: %s", address, err)
        return None


def _with_reachability(hass: HomeAssistant, message: str, address: str) -> str:
    """Message d'erreur complété par l'explication de Home Assistant, si elle existe."""
    reason = async_reachability(hass, address)
    return f"{message} ({reason})" if reason else message


@callback
def async_discovered_radiators(hass: HomeAssistant) -> dict[str, str]:
    """Radiateurs visibles en Bluetooth : adresse -> nom (GOODHOME-XXXX).

    Un radiateur déjà appairé à Home Assistant s'annonce sous son adresse fixe, sans
    son nom mais avec le service GoodHome : il apparaît alors sous son adresse.
    """
    from homeassistant.components import bluetooth

    radiators = {}
    for info in bluetooth.async_discovered_service_info(hass, connectable=True):
        name = info.name or ""
        if name.upper().startswith(LOCAL_NAME_PREFIX):
            radiators[info.address] = name
        elif SERVICE_UUID in info.service_uuids and name.replace("-", ":").upper() in ("", info.address):
            radiators[info.address] = info.address
    return radiators


async def async_list_radiators(hass: HomeAssistant) -> dict[str, str]:
    """Radiateurs visibles, avec le nom retenu par BlueZ pour ceux qui s'annoncent sans nom."""
    radiators = dict(async_discovered_radiators(hass))
    if any(name == address for address, name in radiators.items()):
        try:
            from .ble_agent import async_known_names

            known = await async_known_names()
        except Exception as err:  # noqa: BLE001 - noms en plus, au mieux
            _LOGGER.debug("Cannot read Bluetooth names from BlueZ: %s", err)
            known = {}
        for address, name in radiators.items():
            if name == address and known.get(address.upper(), "").upper().startswith(LOCAL_NAME_PREFIX):
                radiators[address] = known[address.upper()]
    return radiators


def _advertised_name(info) -> str | None:
    """Nom présent dans l'annonce elle-même (et non le nom gardé en mémoire par BlueZ)."""
    return getattr(getattr(info, "advertisement", None), "local_name", None)


def _bluez_address(info) -> str | None:
    """Adresse actuelle de l'appareil selon BlueZ (propriétés jointes à l'annonce ou à l'appareil)."""
    platform = getattr(getattr(info, "advertisement", None), "platform_data", None)
    props = platform[1] if isinstance(platform, tuple) and len(platform) > 1 else None
    if not isinstance(props, dict):
        details = getattr(getattr(info, "device", None), "details", None)
        props = details.get("props") if isinstance(details, dict) else None
    address = props.get("Address") if isinstance(props, dict) else None
    return str(address).upper() if address else None


def _is_at(info, address: str) -> bool:
    """Annonce de l'appareil à cette adresse, rangée sous cette adresse ou sous une ancienne."""
    return info.address.upper() == address.upper() or _bluez_address(info) == address.upper()


@callback
def _async_fresh_device(
    hass: HomeAssistant,
    address: str,
    name: str | None,
    *,
    since: float | None = None,
    exclude: frozenset = frozenset(),
    also_named: str | None = None,
):
    """Appareil d'après la dernière annonce récente du radiateur, None s'il n'en a pas envoyé.

    Avec un nom GOODHOME-XXXX (appairage), seul le nom présent dans l'annonce compte : en mode
    appairage, le radiateur s'annonce sous une nouvelle adresse aléatoire avec son nom, alors que
    BlueZ garde ce nom sur l'adresse d'un ancien appairage que le radiateur n'utilise plus.

    Sinon, l'adresse fixe du radiateur appairé. Bleak garde chaque appareil BlueZ sous l'adresse
    vue la première fois : juste après l'appairage, c'est l'adresse aléatoire du mode appairage,
    même quand BlueZ est passé à l'adresse fixe. Home Assistant range alors les annonces sous
    l'ancienne adresse et ne trouve aucun récepteur pour l'adresse fixe (« no scanner currently
    has it ») jusqu'à son redémarrage. L'entrée sous l'ancienne adresse pointe vers le bon chemin
    BlueZ : elle est reconnue par l'adresse BlueZ jointe à l'annonce, et préférée pour se connecter.

    since / exclude (appairage) : ignorer les annonces d'avant l'oubli de l'ancien appairage, et
    l'adresse oubliée. BlueZ joint aussi le nom gardé en mémoire aux annonces relayées : sans cela,
    une dernière annonce de l'ancienne adresse fixe passerait pour celle du mode appairage.

    also_named (radiateur appairé) : accepter aussi ce nom dans l'annonce. À travers un proxy
    ESPHome, le radiateur n'a pas d'adresse fixe : l'adresse notée à l'appairage change avec le temps.
    """
    from homeassistant.components import bluetooth

    by_name = bool(name) and name.upper().startswith(LOCAL_NAME_PREFIX)
    now = time.monotonic()
    fresh = [
        info
        for info in bluetooth.async_discovered_service_info(hass, connectable=True)
        if (
            _advertised_name(info) == name
            if by_name
            else _is_at(info, address) or (also_named is not None and _advertised_name(info) == also_named)
        )
        and now - info.time < FRESH_ADVERTISEMENT
        and (since is None or info.time >= since)
        and info.address.upper() not in exclude
    ]
    if not fresh:
        return None
    best = max(fresh, key=lambda info: (info.address.upper() != address.upper(), info.time))
    if best.address.upper() != address.upper() and not by_name:
        _LOGGER.debug("Radiator %s known by Bleak as %s, connecting through it", address, best.address)
    return best.device


async def _async_wait_device(
    hass: HomeAssistant,
    address: str,
    name: str | None,
    timeout: float = DEVICE_WAIT,
    *,
    since: float | None = None,
    exclude: frozenset = frozenset(),
    active_scan: bool = False,
    also_named: str | None = None,
):
    """Attendre une annonce récente du radiateur (voir _async_fresh_device).

    active_scan : demander une recherche active si le radiateur n'est pas entendu.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    scanning = False
    while (
        device := _async_fresh_device(hass, address, name, since=since, exclude=exclude, also_named=also_named)
    ) is None:
        if loop.time() >= deadline:
            raise GoodHomeBleNotFound(
                _with_reachability(hass, f"Radiator {name or address} not seen over Bluetooth recently", address)
            )
        if active_scan and not scanning:
            scanning = True
            async_request_active_scan(hass)
        await asyncio.sleep(1)
    return device


async def _async_forget(*addresses: str, name: str | None) -> frozenset[str]:
    """Oublier les appairages BlueZ du radiateur ; renvoie les adresses oubliées.

    Sans dbus-fast (hors Linux), rien à oublier. À travers un proxy ESPHome seul, BlueZ n'a
    aucun appairage du radiateur : aucune adresse oubliée.
    """
    try:
        from .ble_agent import async_remove_bonds
    except ImportError:
        return frozenset()
    forgotten: set[str] = set()
    for address in dict.fromkeys(addresses):
        if removed := await async_remove_bonds(address, name):
            _LOGGER.debug("Forgot previous Bluetooth pairing of %s", name or address)
            forgotten.update(removed)
    return frozenset(forgotten)


def _uses_bluez(device) -> bool:
    """Appareil vu par un adaptateur BlueZ (chemin D-Bus), et non par un proxy ESPHome."""
    details = getattr(device, "details", None)
    return isinstance(details, dict) and "path" in details


def _pairing_agent(device):
    """Agent d'appairage BlueZ pour un appareil vu par BlueZ, rien pour un proxy ESPHome."""
    if not _uses_bluez(device):
        return contextlib.nullcontext()
    from .ble_agent import PairingAgent

    return PairingAgent(device.address)


async def _async_pair_once(hass: HomeAssistant, device, name: str | None) -> tuple[str, str, dict[str, Any]]:
    from bleak.exc import BleakError
    from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

    try:
        # Appairer pendant la connexion : le radiateur coupe les connexions non appairées
        # avant la fin de la découverte des services. L'agent BlueZ accepte la confirmation
        # demandée ; à travers un proxy ESPHome, c'est l'ESP32 qui répond, l'agent ne sert pas.
        bluez = _uses_bluez(device)

        async def _async_connect():
            return await establish_connection(
                BleakClientWithServiceCache,
                device,
                name or device.address,
                max_attempts=3,
                pair=bluez,
            )

        async with _pairing_agent(device):
            bleak_client = await _async_connect()
        if not bluez:
            # pair=True n'arrive pas jusqu'au proxy ESPHome (constaté avec ESPHome 2026.10) :
            # la connexion reste non chiffrée et le radiateur ne répond pas. Appairer ensuite,
            # après avoir oublié la clé d'un essai précédent gardée par l'ESP32 : le radiateur
            # ne l'a plus, et le chiffrement avec cette clé n'aboutit jamais.
            try:
                try:
                    await bleak_client.unpair()
                except (BleakError, NotImplementedError) as err:
                    _LOGGER.debug("No previous ESPHome pairing of %s to forget: %s", name or device.address, err)
                else:
                    # L'ESP32 coupe la connexion en oubliant la clé, sans que is_connected le
                    # sache encore : appairer tout de suite échoue (erreur 102). Se reconnecter.
                    _LOGGER.debug("Forgot previous ESPHome pairing of %s", name or device.address)
                    with contextlib.suppress(Exception):
                        await bleak_client.disconnect()
                    bleak_client = await _async_connect()
                await bleak_client.pair()
            except BaseException:
                await bleak_client.disconnect()
                raise
    except NotImplementedError as err:  # Proxy ESPHome sans la fonction d'appairage
        raise GoodHomeBleError(f"Pairing failed: {err}") from err
    except (BleakError, TimeoutError, OSError) as err:
        if any(text in str(err) for text in REJECTED_ERRORS):
            raise GoodHomeBlePairingRejected(f"Pairing rejected: {err}") from err
        raise GoodHomeBleError(f"Pairing failed: {err}") from err

    # Après l'appairage, le radiateur s'annonce sous son adresse fixe (et non plus aléatoire)
    client = GoodHomeBleClient(hass, bleak_client.address)
    try:
        try:
            # À travers un proxy ESPHome, l'appairage se termine après la réponse de pair() (jusqu'à
            # 30 s) et le radiateur ignore les messages d'avant : renvoyer le premier plus longtemps
            await client.async_adopt(bleak_client, attempts=1 if bluez else PROXY_PAIRING_ATTEMPTS)
        except GoodHomeBleError as err:
            # Juste après l'appairage, le premier échange échoue parfois : se reconnecter
            _LOGGER.debug("First exchange after pairing failed (%s), reconnecting", err)
            await client.async_close()
            await _async_wait_device(hass, client.address, None, active_scan=True)
        devices = await client.async_get_devices()
    finally:
        await client.async_close()
    return client.address, client.serial, devices[client.serial]["state"]


async def async_pair_radiator(
    hass: HomeAssistant, address: str, name: str | None = None
) -> tuple[str, str, dict[str, Any]]:
    """Appairer un radiateur en mode appairage ; renvoie adresse fixe, numéro de série et état."""
    # Repartir d'un appairage neuf : une clé d'un essai précédent bloque tout nouvel appairage.
    # Ensuite, seule une annonce reçue après l'oubli compte, et jamais à une adresse oubliée.
    # Rien n'est oublié (proxy ESPHome seul) : l'adresse actuelle du mode appairage reste valable.
    exclude = await _async_forget(address, name=name)
    since = time.monotonic()
    device = await _async_wait_device(hass, address, name, since=since, exclude=exclude, active_scan=True)
    try:
        return await _async_pair_once(hass, device, name)
    except GoodHomeBlePairingRejected:
        raise
    except GoodHomeBleError as err:
        if not any(text in str(err) for text in STALE_KEY_ERRORS):
            raise
        # Clé que le radiateur n'a plus (créée pendant cet essai) : l'oublier et recommencer
        _LOGGER.info("Stale Bluetooth pairing for %s (%s), pairing again from scratch", name or address, err)
        await _async_forget(address, device.address, name=name)
    device = await _async_wait_device(hass, address, name, since=time.monotonic(), exclude=exclude, active_scan=True)
    return await _async_pair_once(hass, device, name)


class GoodHomeBleClient:
    """Connexion Bluetooth à un radiateur appairé."""

    def __init__(
        self, hass: HomeAssistant, address: str, serial: str | None = None, ble_name: str | None = None
    ) -> None:
        """Initialiser le client (aucune connexion avant la première lecture)."""
        self.hass = hass
        self.address = address
        self.serial = serial
        self.ble_name = ble_name
        # Appelé avec les radiateurs quand celui-ci envoie de lui-même des changements
        self.on_update: Callable[[dict[str, dict]], None] | None = None
        self._client = None
        self._decoder = FrameDecoder()
        self._lock = asyncio.Lock()  # Une opération à la fois (connexion, lecture, commande)
        self._write_lock = asyncio.Lock()
        self._src_id: str | None = None
        self._cmd_id = 0
        self._replies: dict[str, asyncio.Future] = {}
        self._attributes_received = asyncio.Event()
        self._reading = False
        self._reachable = False
        self._state: dict[str, Any] = {}

    def _devices(self) -> dict[str, dict]:
        state = dict(self._state)
        return {
            self.serial: {
                "id": self.serial,
                "name": state.get("roomName") or self.serial,
                "type": "thermostat",
                "connected": self._reachable,
                "state": state,
            }
        }

    async def async_get_devices(self) -> dict[str, dict]:
        """Lire tous les attributs du radiateur."""
        async with self._lock:
            try:
                await self._async_ensure_connected()
                await self._async_read_attributes()
            except GoodHomeBleError:
                self._reachable = False
                # Liaison peut-être encore ouverte mais muette : repartir d'une connexion neuve
                await self.async_close()
                raise
            self._reachable = True
        return self._devices()

    async def async_set_state(self, device_id: str, parameters: dict[str, Any]) -> None:
        """Envoyer des paramètres au format de l'API cloud (ex. {"targetMode": 9})."""
        async with self._lock:
            values = complete_mode_change(parameters, self._state)
            try:
                await self._async_ensure_connected()
                reply = await self._async_command(
                    lambda cmd_id: build_set_attr(self.serial, self._src_id, cmd_id, values)
                )
            except GoodHomeBleError:
                await self.async_close()
                raise
        _LOGGER.debug("Sent %s to radiator %s over Bluetooth, reply: %s", values, self.serial, reply)
        # Relire tout de suite : la confirmation n'attend pas la prochaine relecture
        self.hass.async_create_background_task(self._async_refresh(), f"goodhome ble refresh {self.serial}")

    async def async_identify(self, device_id: str) -> None:
        """Faire biper le radiateur."""
        await self.async_set_state(device_id, {"ping": 1})

    async def async_adopt(self, bleak_client, attempts: int = 1) -> None:
        """Utiliser une connexion déjà ouverte (celle de l'appairage)."""
        async with self._lock:
            await self._async_start(bleak_client, attempts)

    async def async_close(self) -> None:
        """Se déconnecter."""
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.disconnect()
            except Exception as err:  # noqa: BLE001 - déconnexion au mieux
                _LOGGER.debug("Bluetooth disconnect of %s: %s", self.address, err)

    async def _async_refresh(self) -> None:
        try:
            devices = await self.async_get_devices()
        except GoodHomeBleError as err:
            _LOGGER.debug("Refresh after command failed: %s", err)
            return
        if self.on_update is not None:
            self.on_update(devices)

    async def _async_ensure_connected(self) -> None:
        if self._client is not None and self._client.is_connected:
            return
        from bleak.exc import BleakError
        from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

        # Loin de l'adaptateur, les annonces n'arrivent que de temps en temps : attendre la
        # prochaine, Home Assistant ne se connecte qu'à un appareil entendu à l'instant.
        # Les proxys ESPHome en mode auto écoutent en passif : sans recherche active, le nom
        # du radiateur peut tarder plusieurs minutes après un redémarrage de Home Assistant
        device = await _async_wait_device(
            self.hass, self.address, None, timeout=CONNECT_WAIT, active_scan=True, also_named=self.ble_name
        )
        try:
            client = await establish_connection(
                BleakClientWithServiceCache,
                device,
                self.address,
                disconnected_callback=self._on_disconnect,
                max_attempts=3,
            )
        except (BleakError, TimeoutError, OSError) as err:
            raise GoodHomeBleError(
                _with_reachability(self.hass, f"Cannot connect to radiator {self.address}: {err}", self.address)
            ) from err
        # À travers un proxy ESPHome, le chiffrement se termine après la connexion : renvoyer plus longtemps
        await self._async_start(client, 1 if _uses_bluez(device) else PROXY_PAIRING_ATTEMPTS)

    async def _async_start(self, client, attempts: int = 1) -> None:
        """S'abonner aux réponses, puis demander au radiateur son identifiant et le nôtre.

        attempts : nombre d'envois de la demande, quand l'appairage peut finir après la connexion.
        """
        from bleak.exc import BleakError

        self._client = client
        self._decoder = FrameDecoder()
        try:
            await client.start_notify(NOTIFY_UUID, self._on_notify)
            for attempt in range(1, attempts + 1):
                try:
                    status = await self._async_command(
                        lambda cmd_id: build_system_command("system.get_network_status", cmd_id)
                    )
                    break
                except GoodHomeBleError as err:
                    if attempt == attempts or not client.is_connected:
                        raise
                    _LOGGER.debug("No answer yet from %s (%s), asking again", self.address, err)
                    # Abonnement fait avant la fin de l'appairage : le refaire, une fois chiffré
                    with contextlib.suppress(Exception):
                        await client.stop_notify(NOTIFY_UUID)
                    await client.start_notify(NOTIFY_UUID, self._on_notify)
        except (BleakError, OSError) as err:
            raise GoodHomeBleError(f"Bluetooth error with radiator {self.address}: {err}") from err
        # srcID « module.<série> » : le radiateur ; dstID : l'identifiant qu'il nous attribue
        module = str(status.get("srcID") or "")
        if self.serial is None and module.startswith("module."):
            self.serial = module.removeprefix("module.")
        self._src_id = status.get("dstID")
        if not self.serial or not self._src_id:
            raise GoodHomeBleError(f"Unexpected network status from radiator {self.address}: {status}")

    async def _async_read_attributes(self) -> None:
        self._attributes_received.clear()
        self._reading = True
        try:
            await self._async_command(lambda cmd_id: build_get_attr(self.serial, self._src_id, cmd_id))
            try:
                async with asyncio.timeout(ATTRIBUTES_TIMEOUT):
                    await self._attributes_received.wait()
            except TimeoutError as err:
                raise GoodHomeBleError(f"No attributes from radiator {self.serial}") from err
            # Les attributs arrivent en plusieurs messages : attendre la fin
            while True:
                self._attributes_received.clear()
                try:
                    async with asyncio.timeout(ATTRIBUTES_QUIET):
                        await self._attributes_received.wait()
                except TimeoutError:
                    break
        finally:
            self._reading = False

    async def _async_command(self, build: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
        """Envoyer une commande et attendre sa réponse « return »."""
        from bleak.exc import BleakError

        self._cmd_id += 1
        cmd_id = str(self._cmd_id)
        reply = self.hass.loop.create_future()
        self._replies[cmd_id] = reply
        try:
            await self._async_write(build_frame(build(cmd_id)))
            async with asyncio.timeout(COMMAND_TIMEOUT):
                return await reply
        except TimeoutError as err:
            raise GoodHomeBleError(f"No answer from radiator {self.address}") from err
        except (BleakError, OSError) as err:
            raise GoodHomeBleError(f"Bluetooth error with radiator {self.address}: {err}") from err
        finally:
            self._replies.pop(cmd_id, None)

    async def _async_write(self, frame: bytes) -> None:
        if self._client is None:
            raise GoodHomeBleError(f"Not connected to radiator {self.address}")
        async with self._write_lock:
            for chunk in split_chunks(frame):
                await self._client.write_gatt_char(WRITE_UUID, chunk, response=False)
                await asyncio.sleep(CHUNK_DELAY)

    async def _async_ack(self, counter: bytes) -> None:
        try:
            await self._async_write(build_ack(counter))
        except Exception as err:  # noqa: BLE001 - un ACK perdu n'empêche rien
            _LOGGER.debug("ACK to %s failed: %s", self.address, err)

    @callback
    def _on_notify(self, _characteristic, data: bytearray) -> None:
        for frame in self._decoder.feed(bytes(data)):
            if frame.kind == TYPE_NACK:
                _LOGGER.debug("NACK from radiator %s", self.address)
            if frame.kind != TYPE_DATA:
                continue
            self.hass.async_create_task(self._async_ack(frame.counter), eager_start=False)
            self.handle_message(frame.message)

    @callback
    def handle_message(self, message: Any) -> None:
        """Traiter un message du radiateur : réponse à une commande ou nouveaux attributs."""
        if (values := attributes_in(message)) is not None:
            _LOGGER.debug("Attributes from radiator %s: %s", self.serial, values)
            self._state.update(from_radiator(values))
            self._attributes_received.set()
            # Changement envoyé de lui-même par le radiateur (hors lecture demandée)
            if not self._reading and self.serial and self.on_update is not None:
                self.on_update(self._devices())
            return
        if isinstance(message, dict) and message.get("type") == "return":
            reply = self._replies.get(str(message.get("cmdID")))
            if reply is not None and not reply.done():
                reply.set_result(message)
            return
        _LOGGER.debug("Unhandled message from radiator %s: %s", self.address, message)

    @callback
    def _on_disconnect(self, client) -> None:
        # Le radiateur coupe les connexions inactives : on se reconnecte à la prochaine opération
        _LOGGER.debug("Radiator %s disconnected", self.address)
        if self._client is not None and client is not self._client:
            return  # Fin tardive d'une connexion précédente : la nouvelle reste valable
        self._client = None
        for reply in self._replies.values():
            if not reply.done():
                reply.set_exception(GoodHomeBleError(f"Radiator {self.address} disconnected"))
