"""Support for GoodHome Select entities."""
import logging

from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity import DOMAIN, async_add_new_devices, async_wait_for_confirmation, build_device_info

_LOGGER = logging.getLogger(__name__)

# Mapping des modes targetMode selon ESPHome_GoodHome (clé de traduction -> valeur API)
# Voir docs/MODES.md pour le détail de chaque mode
TARGET_MODES = {
    "default": 0,               # Provisoire, retour au mode par défaut
    "manual_comfort": 1,        # Manuel, température confort
    "manual_eco": 2,            # Manuel, température éco
    "manual_frost": 3,          # Manuel, température anti-gel
    "temporary_override": 4,    # Provisoire, température override
    "long_absence": 5,          # Absence de longue durée (holidayTimeout)
    "override": 8,              # Manuel override
    "forced_comfort": 9,        # Forcé confort (retour auto)
    "forced_eco": 10,           # Forcé éco (retour auto)
    "short_absence": 12,        # Absence de courte durée (overrideTime)
    "eco_auto_absence": 30,     # Éco automatique après détection d'absence (20+ min)
    "auto_comfort": 60,         # Mode auto, période de présence
    "auto_eco": 61,             # Mode auto, période d'absence
    "manual": 70,               # Manuel (mise à jour récente)
}

# Mapping inverse pour la lecture
TARGET_MODES_REVERSE = {v: k for k, v in TARGET_MODES.items()}

# Modes affichés mais gérés par le radiateur lui-même, non sélectionnables
READ_ONLY_MODES = {"eco_auto_absence"}

# Options présentées à l'utilisateur (dans l'ordre logique d'utilisation)
TARGET_MODE_OPTIONS = [
    "default",
    "manual_comfort",
    "manual_eco",
    "manual_frost",
    "manual",
    "override",
    "temporary_override",
    "forced_comfort",
    "forced_eco",
    "eco_auto_absence",
    "auto_comfort",
    "auto_eco",
    "short_absence",
    "long_absence",
]

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the GoodHome select platform (YAML)."""
    if discovery_info is None:
        return

    coordinator = hass.data["goodhome"]["coordinator"]
    api = hass.data["goodhome"]["api"]
    
    devices = coordinator.data
    entities = []
    
    for device in devices:
        entities.append(GoodHomeTargetModeSelect(coordinator, api, device))
    
    async_add_entities(entities, True)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the GoodHome select platform (config entry)."""
    coordinator = entry.runtime_data.coordinator
    api = entry.runtime_data.api
    
    def build_entities(devices):
        """Créer les entités de ces radiateurs."""
        entities = []
        for device in devices:
            entities.append(GoodHomeTargetModeSelect(coordinator, api, device))
        return entities

    async_add_new_devices(entry, coordinator, build_entities, async_add_entities)

class GoodHomeTargetModeSelect(CoordinatorEntity, SelectEntity):
    """Representation of a GoodHome Target Mode Select."""
    
    _attr_icon = "mdi:target"
    _attr_has_entity_name = True
    _attr_translation_key = "target_mode"
    
    def __init__(self, coordinator, api, device):
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._api = api
        self._device_id = device["id"]
        self._device_name = device["name"]
        self._attr_unique_id = f"goodhome_target_mode_{device['id']}"
        self._attr_options = TARGET_MODE_OPTIONS
        self._optimistic_state = None
    
    @property
    def device_info(self):
        """Return device info to link this entity to the same device as climate."""
        return build_device_info(self.coordinator, self._device_id, self._device_name)
    
    def _get_device(self):
        """Get the device data from coordinator."""
        for device in self.coordinator.data:
            if device["id"] == self._device_id:
                return device
        return None
    
    @property
    def current_option(self):
        """Return the current selected option."""
        # Si on a un état optimiste, l'utiliser
        if self._optimistic_state is not None:
            return self._optimistic_state
        
        # Sinon, lire depuis l'API
        device = self._get_device()
        if device and device.get("state"):
            target_mode = device["state"].get("targetMode")
            if target_mode is not None:
                # Valeur inconnue : état « inconnu » plutôt qu'un mode erroné
                # (la valeur brute reste visible dans l'attribut target_mode_value)
                return TARGET_MODES_REVERSE.get(target_mode)
        return None
    
    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option not in TARGET_MODES:
            _LOGGER.error("Unknown target mode: %s", option)
            return

        if option in READ_ONLY_MODES:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="read_only_mode",
                translation_placeholders={"option": option},
            )
        
        mode_value = TARGET_MODES[option]
        
        # État optimiste : afficher immédiatement le changement dans l'interface
        self._optimistic_state = option
        self.async_write_ha_state()
        
        _LOGGER.debug("Setting target mode to %s (value: %s) for device %s", option, mode_value, self._device_id)
        
        # Envoyer la commande à l'API
        success = await self.hass.async_add_executor_job(
            self._api.set_parameter,
            self._device_id,
            "targetMode",
            mode_value
        )
        
        if success:
            def check_mode():
                device = self._get_device()
                return bool(device and device.get("state") and device["state"].get("targetMode") == mode_value)

            # Attendre que le radiateur applique la commande, puis abandonner l'état optimiste
            await async_wait_for_confirmation(self.coordinator, check_mode, f"Target mode {option}")
            self._optimistic_state = None
            self.async_write_ha_state()
        else:
            # Échec de la commande, revenir à l'état précédent
            _LOGGER.error("Failed to set target mode to %s", option)
            self._optimistic_state = None
            self.async_write_ha_state()
    
    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        device = self._get_device()
        if device and device.get("state"):
            state = device["state"]
            target_mode = state.get("targetMode")
            
            return {
                "target_mode_value": target_mode,
                "target_temp": state.get("targetTemp"),
                "eco_temp": state.get("ecoTemp"),
                "comfort_temp": state.get("comfTemp"),
                "antifreeze_temp": state.get("antifTemp"),
                "override_temp": state.get("overrideTemp"),
                "manual_mode": state.get("noprog"),
                "self_learning": state.get("selfLearning"),
                "occupancy_status": state.get("occupancyStatus"),
            }
        return {}
