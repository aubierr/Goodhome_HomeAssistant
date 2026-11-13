"""Intégration GoodHome pour Home Assistant."""
import logging
from dataclasses import dataclass

import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN, HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr, issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.translation import async_get_translations
from homeassistant.helpers.typing import ConfigType

from .const import CONF_ADDRESS, CONF_BLE_NAME, CONF_CONNECTION, CONF_SERIAL, CONNECTION_LOCAL, DOMAIN
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
    """Données d'exécution d'une entrée GoodHome (entry.runtime_data)."""

    coordinator: GoodHomeCoordinator
    push: GoodHomePushClient | None  # Écoute temps réel du cloud, None en mode local


type GoodHomeConfigEntry = ConfigEntry[GoodHomeData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Enregistrer le service, et importer une ancienne configuration YAML."""

    async def async_identify_device(call: ServiceCall) -> None:
        device_id = call.data["device_id"]
        # Appareil Home Assistant (sélecteur), ou identifiant GoodHome des anciennes automatisations
        if (device := dr.async_get(hass).async_get(device_id)) is not None:
            device_id = next(
                (identifier for domain, identifier in device.identifiers if domain == DOMAIN), device_id
            )
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
    """Connecter le compte (ou le radiateur en local), lire les radiateurs et écouter le temps réel."""
    if entry.data.get(CONF_CONNECTION) == CONNECTION_LOCAL:
        return await _async_setup_local_entry(hass, entry)

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

    # Écoute temps réel, arrêtée automatiquement au déchargement
    push_client = GoodHomePushClient(session, client, coordinator.async_apply_push_event)
    entry.runtime_data = GoodHomeData(coordinator=coordinator, push=push_client)
    entry.async_create_background_task(hass, push_client.run(), "goodhome_push")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_setup_local_entry(hass: HomeAssistant, entry: GoodHomeConfigEntry) -> bool:
    """Radiateur appairé en Bluetooth : les changements arrivent par notification."""
    from .ble_client import GoodHomeBleClient

    client = GoodHomeBleClient(
        hass, entry.data[CONF_ADDRESS], entry.data[CONF_SERIAL], entry.data.get(CONF_BLE_NAME)
    )
    coordinator = GoodHomeCoordinator(hass, entry, client)
    client.on_update = coordinator.async_set_updated_data
    entry.runtime_data = GoodHomeData(coordinator=coordinator, push=None)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Ne pas attendre le radiateur : se connecter peut durer une minute ou échouer (radiateur
    # éteint, proxy saturé). L'installation ne bloque plus le démarrage de Home Assistant, les
    # entités apparaissent dès la première réponse, et la relecture périodique réessaie sinon.
    entry.async_create_background_task(hass, coordinator.async_refresh(), f"goodhome first refresh {entry.title}")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GoodHomeConfigEntry) -> bool:
    """Décharger le compte (ou le radiateur)."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and entry.data.get(CONF_CONNECTION) == CONNECTION_LOCAL:
        await entry.runtime_data.coordinator.client.async_close()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: GoodHomeConfigEntry) -> None:
    """Radiateur local supprimé : le laisser être redécouvert sans redémarrer Home Assistant.

    Le Bluetooth de Home Assistant ne propose un appareil qu'une fois par adresse : sans cela, la
    carte « Découvertes » ne reviendrait pas pour un radiateur remis en mode appairage.
    """
    if entry.data.get(CONF_CONNECTION) != CONNECTION_LOCAL:
        return
    from .ble_client import async_discovered_radiators, async_rediscover

    name = entry.data.get(CONF_BLE_NAME)
    try:
        current = [address for address, found in async_discovered_radiators(hass).items() if name and found == name]
    except Exception as err:  # noqa: BLE001 - la suppression ne doit jamais échouer
        _LOGGER.debug("Cannot list Bluetooth radiators: %s", err)
        current = []
    async_rediscover(hass, entry.data.get(CONF_ADDRESS), *current)

    await _async_remind_forget_mobile(hass, entry)


async def _async_remind_forget_mobile(hass: HomeAssistant, entry: GoodHomeConfigEntry) -> None:
    """Rappeler de supprimer aussi le mobile sur le radiateur (sinon il peut refuser un nouvel appairage)."""
    from homeassistant.components import persistent_notification

    try:
        translations = await async_get_translations(hass, hass.config.language, "exceptions", [DOMAIN])
        message = translations[f"component.{DOMAIN}.exceptions.forget_mobile.message"]
        persistent_notification.async_create(
            hass,
            message.format(name=entry.title),
            title="GoodHome",
            notification_id=f"{DOMAIN}_forget_mobile_{entry.entry_id}",
        )
    except Exception as err:  # noqa: BLE001 - la suppression ne doit jamais échouer
        _LOGGER.debug("Cannot create the removal reminder: %s", err)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: GoodHomeConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Autoriser la suppression d'un radiateur qui n'existe plus dans le compte GoodHome.

    En local, l'entrée ne contient que ce radiateur : supprimer l'appareil supprime l'entrée,
    au lieu d'un refus incompréhensible (et l'appareil reviendrait à la relecture suivante).
    """
    if entry.data.get(CONF_CONNECTION) == CONNECTION_LOCAL:
        hass.async_create_task(hass.config_entries.async_remove(entry.entry_id))
        return True
    current_ids = set(entry.runtime_data.coordinator.data or {})
    return not any(
        domain == DOMAIN and device_id in current_ids for domain, device_id in device_entry.identifiers
    )
