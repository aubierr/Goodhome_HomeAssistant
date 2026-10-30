"""Helpers partagés par les entités GoodHome."""
from homeassistant.helpers.device_registry import DeviceInfo

DOMAIN = "goodhome"


def _as_str(value):
    """Convertir une version en texte (l'API peut renvoyer des nombres)."""
    return str(value) if value is not None else None


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
