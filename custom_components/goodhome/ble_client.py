"""Client Bluetooth local d'un radiateur GoodHome.

Même interface que le client cloud (async_get_devices, async_set_state, async_identify) :
le coordinator et les entités fonctionnent de la même façon dans les deux modes.
Le Bluetooth de Home Assistant n'est importé qu'ici, pour ne pas l'imposer au mode cloud.
"""
from __future__ import annotations

import asyncio
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


async def _async_wait_device(hass: HomeAssistant, address: str, name: str | None, timeout: float = DEVICE_WAIT):
    """Appareil Bluetooth du radiateur d'après sa dernière annonce récente, sous son adresse ou son nom.

    Seule une annonce récente compte : BlueZ garde aussi le nom d'un ancien appairage sur
    une adresse que le radiateur n'utilise plus.
    """
    from homeassistant.components import bluetooth

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        now = time.monotonic()
        fresh = [
            info
            for info in bluetooth.async_discovered_service_info(hass, connectable=True)
            if (info.address == address or (name and info.name == name)) and now - info.time < FRESH_ADVERTISEMENT
        ]
        if fresh:
            return max(fresh, key=lambda info: info.time).device
        if loop.time() >= deadline:
            raise GoodHomeBleNotFound(f"Radiator {name or address} not seen over Bluetooth recently")
        await asyncio.sleep(1)


async def _async_forget(*addresses: str, name: str | None) -> None:
    """Oublier les appairages BlueZ du radiateur (sans dbus-fast hors Linux : rien à oublier)."""
    try:
        from .ble_agent import async_remove_bonds
    except ImportError:
        return
    for address in dict.fromkeys(addresses):
        if await async_remove_bonds(address, name):
            _LOGGER.debug("Forgot previous Bluetooth pairing of %s", name or address)


async def _async_pair_once(hass: HomeAssistant, device) -> tuple[str, str, dict[str, Any]]:
    from bleak.exc import BleakError
    from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

    from .ble_agent import PairingAgent

    try:
        # Appairer pendant la connexion : le radiateur coupe les connexions non appairées
        # avant la fin de la découverte des services. L'agent accepte la confirmation demandée.
        async with PairingAgent(device.address):
            bleak_client = await establish_connection(
                BleakClientWithServiceCache, device, device.name or device.address, max_attempts=3, pair=True
            )
    except (BleakError, TimeoutError, OSError) as err:
        if any(text in str(err) for text in REJECTED_ERRORS):
            raise GoodHomeBlePairingRejected(f"Pairing rejected: {err}") from err
        raise GoodHomeBleError(f"Pairing failed: {err}") from err

    # Après l'appairage, le radiateur s'annonce sous son adresse fixe (et non plus aléatoire)
    client = GoodHomeBleClient(hass, bleak_client.address)
    try:
        try:
            await client.async_adopt(bleak_client)
        except GoodHomeBleError as err:
            # Juste après l'appairage, le premier échange échoue parfois : se reconnecter
            _LOGGER.debug("First exchange after pairing failed (%s), reconnecting", err)
            await client.async_close()
            await _async_wait_device(hass, client.address, None)
        devices = await client.async_get_devices()
    finally:
        await client.async_close()
    return client.address, client.serial, devices[client.serial]["state"]


async def async_pair_radiator(
    hass: HomeAssistant, address: str, name: str | None = None
) -> tuple[str, str, dict[str, Any]]:
    """Appairer un radiateur en mode appairage ; renvoie adresse fixe, numéro de série et état."""
    # Repartir d'un appairage neuf : une clé d'un essai précédent bloque tout nouvel appairage
    await _async_forget(address, name=name)
    device = await _async_wait_device(hass, address, name)
    try:
        return await _async_pair_once(hass, device)
    except GoodHomeBlePairingRejected:
        raise
    except GoodHomeBleError as err:
        if not any(text in str(err) for text in STALE_KEY_ERRORS):
            raise
        # Clé que le radiateur n'a plus (créée pendant cet essai) : l'oublier et recommencer
        _LOGGER.info("Stale Bluetooth pairing for %s (%s), pairing again from scratch", name or address, err)
        await _async_forget(address, device.address, name=name)
    device = await _async_wait_device(hass, address, name)
    return await _async_pair_once(hass, device)


class GoodHomeBleClient:
    """Connexion Bluetooth à un radiateur appairé."""

    def __init__(self, hass: HomeAssistant, address: str, serial: str | None = None) -> None:
        """Initialiser le client (aucune connexion avant la première lecture)."""
        self.hass = hass
        self.address = address
        self.serial = serial
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
                raise
            self._reachable = True
        return self._devices()

    async def async_set_state(self, device_id: str, parameters: dict[str, Any]) -> None:
        """Envoyer des paramètres au format de l'API cloud (ex. {"targetMode": 9})."""
        async with self._lock:
            await self._async_ensure_connected()
            await self._async_command(lambda cmd_id: build_set_attr(self.serial, self._src_id, cmd_id, parameters))
        _LOGGER.debug("Sent %s to radiator %s over Bluetooth", parameters, self.serial)
        # Relire tout de suite : la confirmation n'attend pas la prochaine relecture
        self.hass.async_create_background_task(self._async_refresh(), f"goodhome ble refresh {self.serial}")

    async def async_identify(self, device_id: str) -> None:
        """Faire biper le radiateur."""
        await self.async_set_state(device_id, {"ping": 1})

    async def async_adopt(self, bleak_client) -> None:
        """Utiliser une connexion déjà ouverte (celle de l'appairage)."""
        async with self._lock:
            await self._async_start(bleak_client)

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
        from homeassistant.components import bluetooth

        # Loin de l'adaptateur, les annonces n'arrivent que de temps en temps : attendre la
        # prochaine, Home Assistant ne se connecte qu'à un appareil entendu à l'instant
        device = await _async_wait_device(self.hass, self.address, None, timeout=CONNECT_WAIT)
        try:
            client = await establish_connection(
                BleakClientWithServiceCache,
                device,
                self.address,
                disconnected_callback=self._on_disconnect,
                max_attempts=3,
                ble_device_callback=lambda: (
                    bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True) or device
                ),
            )
        except (BleakError, TimeoutError, OSError) as err:
            raise GoodHomeBleError(f"Cannot connect to radiator {self.address}: {err}") from err
        await self._async_start(client)

    async def _async_start(self, client) -> None:
        """S'abonner aux réponses, puis demander au radiateur son identifiant et le nôtre."""
        from bleak.exc import BleakError

        self._client = client
        self._decoder = FrameDecoder()
        try:
            await client.start_notify(NOTIFY_UUID, self._on_notify)
            status = await self._async_command(
                lambda cmd_id: build_system_command("system.get_network_status", cmd_id)
            )
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
    def _on_disconnect(self, _client) -> None:
        # Le radiateur coupe les connexions inactives : on se reconnecte à la prochaine opération
        _LOGGER.debug("Radiator %s disconnected", self.address)
        self._client = None
        for reply in self._replies.values():
            if not reply.done():
                reply.set_exception(GoodHomeBleError(f"Radiator {self.address} disconnected"))
