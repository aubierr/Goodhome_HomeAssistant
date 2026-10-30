"""Coordinator GoodHome : relecture de l'API et événements temps réel."""
import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONFIRMATION_TIMEOUT, DOMAIN, UPDATE_INTERVAL
from .goodhome_api import GoodHomeAuthError, GoodHomeClient, GoodHomeError

_LOGGER = logging.getLogger(__name__)

# Événements Socket.io qui portent des champs de « state » (voir push.py)
PUSH_EVENTS = ("setState", "report")


class GoodHomeCoordinator(DataUpdateCoordinator[dict[str, dict]]):
    """Données de tous les radiateurs d'un compte, indexées par identifiant."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: GoodHomeClient):
        """Initialiser le coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.client = client

    async def _async_update_data(self):
        try:
            return await self.client.async_get_devices()
        except GoodHomeAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except GoodHomeError as err:
            raise UpdateFailed(str(err)) from err

    @callback
    def async_apply_push_event(self, name, payload):
        """Appliquer un événement Socket.io : seuls les champs modifiés sont envoyés."""
        if name not in PUSH_EVENTS or not isinstance(payload, dict):
            _LOGGER.debug("Ignored push event %s", name)
            return
        device_id = payload.get("objectId")
        changes = payload.get("data")
        devices = self.data or {}
        if payload.get("objectType") != "device" or not isinstance(changes, dict) or device_id not in devices:
            return

        device = devices[device_id]
        # Nouveaux objets plutôt qu'une modification sur place : le cache HTTP du client les partage
        self.data = {**devices, device_id: {**device, "state": {**device["state"], **changes}}}
        # Sans async_set_updated_data, qui repousserait la relecture REST de secours
        self.async_update_listeners()
        _LOGGER.debug("Push %s for %s: %s", name, device_id, changes)

    async def async_wait_for(self, check, description):
        """Attendre que les données confirment une commande.

        Le radiateur applique une commande en 45 s à 2 min (mesuré) ; la confirmation
        arrive par un événement setState ou par la relecture. False après CONFIRMATION_TIMEOUT.
        """
        if check():
            return True

        confirmed = asyncio.Event()

        @callback
        def _check_update():
            if check():
                confirmed.set()

        unsubscribe = self.async_add_listener(_check_update)
        try:
            async with asyncio.timeout(CONFIRMATION_TIMEOUT):
                await confirmed.wait()
        except TimeoutError:
            _LOGGER.warning("%s not confirmed after %ss", description, CONFIRMATION_TIMEOUT)
            return False
        finally:
            unsubscribe()
        _LOGGER.debug("%s confirmed", description)
        return True
