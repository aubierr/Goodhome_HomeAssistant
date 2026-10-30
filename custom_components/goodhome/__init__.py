"""GoodHome Integration pour Home Assistant."""
import logging
import asyncio
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers import discovery
from homeassistant.helpers.device_registry import DeviceEntry

from .goodhome_api import GoodHomeAPI, GoodHomeAuthError, GoodHomeConnectionError, GoodHomeError

_LOGGER = logging.getLogger(__name__)

DOMAIN = "goodhome"
PLATFORMS = [Platform.CLIMATE, Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH, Platform.SELECT, Platform.NUMBER]


@dataclass
class GoodHomeData:
    """Données d'exécution d'un compte GoodHome (entry.runtime_data)."""

    coordinator: DataUpdateCoordinator
    api: GoodHomeAPI


type GoodHomeConfigEntry = ConfigEntry[GoodHomeData]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the GoodHome component from yaml configuration."""
    hass.data.setdefault(DOMAIN, {})

    if DOMAIN not in config:
        return True

    conf = config[DOMAIN]
    user_id = conf.get("user_id")
    token = conf.get("token")
    email = conf.get("email")
    password = conf.get("password")

    if (user_id and token) or (email and password):
        api = GoodHomeAPI(user_id, token, email, password)

        # Si email/password fournis, obtenir un nouveau token
        if email and password and not token:
            try:
                if not await hass.async_add_executor_job(api.login):
                    _LOGGER.error("GoodHome login failed: invalid credentials")
                    return False
            except GoodHomeConnectionError as err:
                _LOGGER.error("GoodHome login failed: %s", err)
                return False

        async def async_update_data():
            """Fetch data from API."""
            try:
                devices = await hass.async_add_executor_job(api.get_devices)
                return devices
            except GoodHomeError as err:
                raise UpdateFailed(f"Error communicating with API: {err}") from err

        coordinator = DataUpdateCoordinator(
            hass,
            _LOGGER,
            name="goodhome",
            update_method=async_update_data,
            update_interval=timedelta(seconds=60),
        )

        # Pour une configuration YAML, utiliser async_refresh au lieu de async_config_entry_first_refresh
        await coordinator.async_refresh()
        if not coordinator.last_update_success:
            _LOGGER.error("GoodHome initial data fetch failed")
            return False

        hass.data[DOMAIN]["coordinator"] = coordinator
        hass.data[DOMAIN]["api"] = api

        # Register identify service
        async def async_identify_device(call):
            """Handle the identify device service call."""
            device_id = call.data.get("device_id")
            if device_id:
                await hass.async_add_executor_job(api.identify_device, device_id)

        hass.services.async_register(DOMAIN, "identify_device", async_identify_device)

        # Charger les plateformes
        for platform in PLATFORMS:
            hass.async_create_task(
                discovery.async_load_platform(hass, platform, DOMAIN, {}, config)
            )

    return True

async def async_setup_entry(hass: HomeAssistant, entry: GoodHomeConfigEntry) -> bool:
    """Set up GoodHome from a config entry."""
    email = entry.data.get("email")
    password = entry.data.get("password")
    user_id = entry.data.get("user_id")
    token = entry.data.get("token")

    # Priorité à email/password si disponibles
    if email and password:
        api = GoodHomeAPI(None, None, email, password)
        # Obtenir le token
        try:
            if not await hass.async_add_executor_job(api.login):
                raise ConfigEntryAuthFailed("Invalid GoodHome credentials")
        except GoodHomeConnectionError as err:
            raise ConfigEntryNotReady(f"Cannot connect to GoodHome: {err}") from err
    else:
        api = GoodHomeAPI(user_id, token)

    async def async_update_data():
        """Fetch data from API."""
        try:
            devices = await hass.async_add_executor_job(api.get_devices)
            return devices
        except GoodHomeAuthError as err:
            raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
        except GoodHomeError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="goodhome",
        config_entry=entry,
        update_method=async_update_data,
        update_interval=timedelta(seconds=60),
    )

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = GoodHomeData(coordinator=coordinator, api=api)

    if not hass.services.has_service(DOMAIN, "identify_device"):
        async def async_identify_device(call):
            """Handle the identify device service call."""
            device_id = call.data.get("device_id")
            if not device_id:
                return
            # Trouver le compte (config entry) qui possède cet appareil
            for config_entry in hass.config_entries.async_entries(DOMAIN):
                data = getattr(config_entry, "runtime_data", None)
                if not isinstance(data, GoodHomeData):
                    continue
                devices = data.coordinator.data or []
                if any(device["id"] == device_id for device in devices):
                    await hass.async_add_executor_job(data.api.identify_device, device_id)
                    return
            _LOGGER.warning("GoodHome device %s not found", device_id)

        hass.services.async_register(DOMAIN, "identify_device", async_identify_device)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: GoodHomeConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Autoriser la suppression d'un radiateur qui n'existe plus dans le compte GoodHome."""
    current_ids = {device["id"] for device in entry.runtime_data.coordinator.data or []}
    return not any(
        domain == DOMAIN and device_id in current_ids
        for domain, device_id in device_entry.identifiers
    )

async def async_unload_entry(hass: HomeAssistant, entry: GoodHomeConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
