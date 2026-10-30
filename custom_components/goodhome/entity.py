"""Helpers partagés par les entités GoodHome."""
import asyncio
import logging

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONFIRMATION_TIMEOUT

_LOGGER = logging.getLogger(__name__)

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


async def async_wait_for_confirmation(coordinator, check, description):
    """Attendre que les données du coordinator confirment une commande.

    La confirmation arrive par l'écoute Socket.io (événement setState) ou, en
    secours, par la relecture REST. Renvoie False après CONFIRMATION_TIMEOUT.
    """
    if check():
        return True

    confirmed = asyncio.Event()

    @callback
    def _check_update():
        if check():
            confirmed.set()

    unsubscribe = coordinator.async_add_listener(_check_update)
    try:
        async with asyncio.timeout(CONFIRMATION_TIMEOUT):
            await confirmed.wait()
        _LOGGER.debug("%s confirmed", description)
        return True
    except TimeoutError:
        _LOGGER.warning("%s not confirmed after %ss", description, CONFIRMATION_TIMEOUT)
        return False
    finally:
        unsubscribe()


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
