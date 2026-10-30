"""Helpers partagés par les entités GoodHome."""
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo

DOMAIN = "goodhome"


def _as_str(value):
    """Convertir une version en texte (l'API peut renvoyer des nombres)."""
    return str(value) if value is not None else None


def async_add_new_devices(entry, coordinator, build_entities, async_add_entities):
    """Ajouter les entités des radiateurs présents, puis de ceux qui apparaissent ensuite.

    Un radiateur ajouté dans l'app GoodHome apparaît à la mise à jour suivante
    du coordinator, sans redémarrer Home Assistant.
    """
    known_ids = set()

    @callback
    def _add_new_devices():
        new_devices = [d for d in coordinator.data or [] if d["id"] not in known_ids]
        if not new_devices:
            return
        known_ids.update(d["id"] for d in new_devices)
        async_add_entities(build_entities(new_devices))

    _add_new_devices()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_devices))


def build_device_info(coordinator, device_id, name):
    """Construire le DeviceInfo d'un thermostat à partir des données du coordinator."""
    state = {}
    for device in coordinator.data or []:
        if device["id"] == device_id:
            state = device.get("state") or {}
            break

    return DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        name=name,
        manufacturer="GoodHome",
        model=state.get("codeName") or "Thermostat",
        sw_version=_as_str(state.get("fwVer")),
        hw_version=_as_str(state.get("HwVer")),
    )
