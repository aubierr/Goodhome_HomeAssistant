"""Agent d'appairage BlueZ temporaire : accepte la confirmation demandée par le radiateur.

Sans agent, BlueZ annule l'appairage (« No agent available for request type 2 »).
L'agent n'existe que pendant l'appairage et refuse tout autre appareil.
Ce module n'utilise pas « from __future__ import annotations » : dbus-fast lit les
signatures D-Bus dans les annotations.
"""
import logging

from dbus_fast import BusType, DBusError
from dbus_fast.aio import MessageBus
from dbus_fast.service import ServiceInterface, method

_LOGGER = logging.getLogger(__name__)

AGENT_PATH = "/org/goodhome/agent"
REJECTED = "org.bluez.Error.Rejected"


class _ConfirmAgent(ServiceInterface):
    """Répond « oui » pour le radiateur en cours d'appairage, comme l'utilisateur sur son téléphone."""

    def __init__(self, address: str) -> None:
        super().__init__("org.bluez.Agent1")
        # Chemin D-Bus BlueZ : .../dev_AA_BB_CC_DD_EE_FF
        self._device_suffix = "dev_" + address.upper().replace(":", "_")

    def _check(self, device: str) -> None:
        if not device.endswith(self._device_suffix):
            _LOGGER.warning("Rejected Bluetooth pairing request from %s", device)
            raise DBusError(REJECTED, "Not the GoodHome radiator being paired")

    @method()
    def Release(self):  # noqa: N802 - noms imposés par BlueZ
        _LOGGER.debug("Pairing agent released")

    @method()
    def RequestConfirmation(self, device: "o", passkey: "u"):  # noqa: F821, N802
        self._check(device)
        _LOGGER.debug("Pairing confirmation %06d accepted for %s", passkey, device)

    @method()
    def RequestAuthorization(self, device: "o"):  # noqa: F821, N802
        self._check(device)
        _LOGGER.debug("Pairing authorization accepted for %s", device)

    @method()
    def AuthorizeService(self, device: "o", uuid: "s"):  # noqa: F821, N802
        self._check(device)

    @method()
    def Cancel(self):  # noqa: N802
        _LOGGER.debug("Pairing cancelled by BlueZ")


async def async_known_names() -> dict[str, str]:
    """Noms Bluetooth retenus par BlueZ : adresse -> nom (GOODHOME-XXXX).

    Un radiateur appairé s'annonce sans son nom ; BlueZ s'en souvient depuis l'appairage.
    """
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    try:
        introspection = await bus.introspect("org.bluez", "/")
        manager = bus.get_proxy_object("org.bluez", "/", introspection).get_interface(
            "org.freedesktop.DBus.ObjectManager"
        )
        names = {}
        for interfaces in (await manager.call_get_managed_objects()).values():
            device = interfaces.get("org.bluez.Device1")
            if device is not None and "Address" in device and "Name" in device:
                names[device["Address"].value.upper()] = device["Name"].value
        return names
    finally:
        bus.disconnect()


async def async_remove_bonds(address: str, name: str | None) -> list[str]:
    """Oublier les appairages BlueZ d'un radiateur (par adresse ou par nom) ; renvoie leurs adresses.

    Un appairage raté laisse une clé que le radiateur n'a plus : chaque nouvel essai échoue
    alors avec « br-connection-key-missing ». Repartir d'un appairage neuf règle le problème.
    """
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    removed = []
    try:
        introspection = await bus.introspect("org.bluez", "/")
        manager = bus.get_proxy_object("org.bluez", "/", introspection).get_interface(
            "org.freedesktop.DBus.ObjectManager"
        )
        for path, interfaces in (await manager.call_get_managed_objects()).items():
            device = interfaces.get("org.bluez.Device1")
            if device is None or not device.get("Paired") or not device["Paired"].value:
                continue
            values = {key: device[key].value for key in ("Address", "Name", "Alias") if key in device}
            if values.get("Address", "").upper() != address.upper() and name not in (values.get("Name"), values.get("Alias")):
                continue
            adapter_path = device["Adapter"].value
            adapter_introspection = await bus.introspect("org.bluez", adapter_path)
            adapter = bus.get_proxy_object("org.bluez", adapter_path, adapter_introspection).get_interface(
                "org.bluez.Adapter1"
            )
            await adapter.call_remove_device(path)
            removed.append(values.get("Address", "").upper())
            _LOGGER.debug("Removed stale Bluetooth pairing %s", path)
    finally:
        bus.disconnect()
    return removed


class PairingAgent:
    """Enregistrer l'agent par défaut le temps d'un appairage, puis le retirer."""

    def __init__(self, address: str) -> None:
        self._address = address
        self._bus: MessageBus | None = None
        self._manager = None

    async def __aenter__(self) -> "PairingAgent":
        self._bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        self._bus.export(AGENT_PATH, _ConfirmAgent(self._address))
        introspection = await self._bus.introspect("org.bluez", "/org/bluez")
        bluez = self._bus.get_proxy_object("org.bluez", "/org/bluez", introspection)
        self._manager = bluez.get_interface("org.bluez.AgentManager1")
        await self._manager.call_register_agent(AGENT_PATH, "DisplayYesNo")
        await self._manager.call_request_default_agent(AGENT_PATH)
        _LOGGER.debug("Pairing agent registered for %s", self._address)
        return self

    async def __aexit__(self, *_exc) -> None:
        try:
            if self._manager is not None:
                await self._manager.call_unregister_agent(AGENT_PATH)
        except Exception as err:  # noqa: BLE001 - retrait au mieux
            _LOGGER.debug("Removing the BlueZ pairing agent: %s", err)
        finally:
            if self._bus is not None:
                self._bus.disconnect()
