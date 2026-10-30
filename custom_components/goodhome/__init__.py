"""Intégration GoodHome pour Home Assistant."""
import logging
from dataclasses import dataclass

import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN, HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv, issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .coordinator import GoodHomeCoordinator
from .goodhome_api import GoodHomeAuthError, GoodHomeClient, GoodHomeError
from .push import GoodHomePushClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

# Configuration YAML : seulement importée vers l'interface (voir async_setup)
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {vol.Optional(CONF_EMAIL): cv.string, vol.Optional(CONF_PASSWORD): cv.string},
            extra=vol.ALLOW_EXTRA,
        )
    },
    extra=vol.ALLOW_EXTRA,
)

SERVICE_IDENTIFY = "identify_device"
SERVICE_IDENTIFY_SCHEMA = vol.Schema({vol.Required("device_id"): cv.string})


@dataclass
class GoodHomeData:
    """Données d'exécution d'un compte GoodHome (entry.runtime_data)."""

    coordinator: GoodHomeCoordinator


type GoodHomeConfigEntry = ConfigEntry[GoodHomeData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Enregistrer le service, et importer une ancienne configuration YAML."""

    async def async_identify_device(call: ServiceCall) -> None:
        device_id = call.data["device_id"]
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.state is not ConfigEntryState.LOADED:
                continue
            coordinator = entry.runtime_data.coordinator
            if device_id in (coordinator.data or {}):
                try:
                    await coordinator.client.async_identify(device_id)
                except GoodHomeError as err:
                    raise HomeAssistantError(
                        translation_domain=DOMAIN,
                        translation_key="command_failed",
                        translation_placeholders={"error": str(err)},
                    ) from err
                return
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="device_not_found",
            translation_placeholders={"device_id": device_id},
        )

    hass.services.async_register(DOMAIN, SERVICE_IDENTIFY, async_identify_device, SERVICE_IDENTIFY_SCHEMA)

    if DOMAIN in config:
        conf = config[DOMAIN]
        # L'ancienne connexion par user_id/token ne peut pas être importée : elle doit être refaite
        if CONF_EMAIL in conf and CONF_PASSWORD in conf:
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": SOURCE_IMPORT},
                    data={CONF_EMAIL: conf[CONF_EMAIL], CONF_PASSWORD: conf[CONF_PASSWORD]},
                )
            )
        ir.async_create_issue(
            hass,
            HOMEASSISTANT_DOMAIN,
            f"deprecated_yaml_{DOMAIN}",
            is_fixable=False,
            breaks_in_ha_version=None,
            severity=ir.IssueSeverity.WARNING,
            translation_key="deprecated_yaml",
            translation_placeholders={"domain": DOMAIN, "integration_title": "GoodHome"},
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: GoodHomeConfigEntry) -> bool:
    """Connecter le compte, lire les radiateurs et écouter le temps réel."""
    session = async_get_clientsession(hass)
    client = GoodHomeClient(session, entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])
    try:
        await client.async_login()
    except GoodHomeAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except GoodHomeError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = GoodHomeCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = GoodHomeData(coordinator=coordinator)

    # Écoute temps réel, arrêtée automatiquement au déchargement
    push_client = GoodHomePushClient(session, client, coordinator.async_apply_push_event)
    entry.async_create_background_task(hass, push_client.run(), "goodhome_push")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GoodHomeConfigEntry) -> bool:
    """Décharger le compte."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: GoodHomeConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Autoriser la suppression d'un radiateur qui n'existe plus dans le compte GoodHome."""
    current_ids = set(entry.runtime_data.coordinator.data or {})
    return not any(
        domain == DOMAIN and device_id in current_ids for domain, device_id in device_entry.identifiers
    )
