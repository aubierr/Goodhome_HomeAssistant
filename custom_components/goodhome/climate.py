"""GoodHome Climate Platform."""
import logging
import asyncio
from typing import Any, Callable

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
    PRESET_AWAY,
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_SLEEP,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEBOUNCE_DELAY
from .entity import async_add_new_devices, async_wait_for_confirmation, build_device_info

_LOGGER = logging.getLogger(__name__)

PRESET_MANUAL = "manual"

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the GoodHome climate platform (YAML config)."""
    coordinator = hass.data["goodhome"]["coordinator"]
    api = hass.data["goodhome"]["api"]
    
    devices = coordinator.data
    entities = []
    
    for device in devices:
        entities.append(GoodHomeClimate(coordinator, api, device))
    
    async_add_entities(entities, True)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the GoodHome climate platform (config entry)."""
    coordinator = entry.runtime_data.coordinator
    api = entry.runtime_data.api
    
    def build_entities(devices):
        """Créer les entités de ces radiateurs."""
        entities = []
        for device in devices:
            entities.append(GoodHomeClimate(coordinator, api, device))
        return entities

    async_add_new_devices(entry, coordinator, build_entities, async_add_entities)

class GoodHomeClimate(CoordinatorEntity, ClimateEntity):
    """Representation of a GoodHome Climate device."""
    
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes = [PRESET_COMFORT, PRESET_ECO, PRESET_MANUAL, PRESET_AWAY, PRESET_SLEEP]
    _attr_min_temp = 7
    _attr_max_temp = 30
    _attr_target_temperature_step = 0.5
    
    def __init__(self, coordinator, api, device):
        """Initialize the climate device."""
        super().__init__(coordinator)
        self._api = api
        self._device_id = device["id"]
        self._device_name = device["name"]
        # Entité principale de l'appareil : elle porte le nom de l'appareil
        self._attr_has_entity_name = True
        self._attr_name = None
        self._attr_unique_id = f"goodhome_climate_{device['id']}"
        self._debounce_task = None
        self._pending_temperature = None
        self._pending_hvac_mode = None
        self._pending_preset_mode = None
        
    @property
    def device_info(self):
        """Return device info."""
        return build_device_info(self.coordinator, self._device_id, self._device_name)
    
    @property
    def available(self):
        """Return True if entity is available."""
        device = self._get_device()
        if device:
            return device.get("connected", False)
        return False
    
    def _get_device(self):
        """Get device from coordinator data."""
        for device in self.coordinator.data:
            if device["id"] == self._device_id:
                return device
        return None
    
    async def _wait_for_confirmation(self, check_function: Callable[[], bool], description: str) -> bool:
        """Attendre que le radiateur confirme un changement."""
        return await async_wait_for_confirmation(self.coordinator, check_function, description)
    
    @property
    def current_temperature(self):
        """Return the current temperature."""
        device = self._get_device()
        if device and device.get("state"):
            return device["state"].get("currentTemp")
        return None
    
    @property
    def current_humidity(self):
        """Return the current humidity."""
        device = self._get_device()
        if device and device.get("state"):
            humidity = device["state"].get("humidity")
            if humidity is not None:
                return humidity
        return None
    
    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        # Si une température est en attente, l'afficher immédiatement
        if self._pending_temperature is not None:
            return self._pending_temperature
        
        device = self._get_device()
        if device and device.get("state"):
            return device["state"].get("targetTemp")
        return None
    
    @property
    def hvac_mode(self):
        """Return hvac operation ie. heat, cool mode."""
        # Si un mode est en attente, l'afficher immédiatement
        if self._pending_hvac_mode is not None:
            return self._pending_hvac_mode
        
        device = self._get_device()
        if device and device.get("state"):
            mode = device["state"].get("targetMode", 1)
            # Mode 3 = anti-gel manuel = OFF (seul mode d'arrêt, comme ESPHome_GoodHome)
            if mode == 3:
                return HVACMode.OFF
            return HVACMode.HEAT
        return HVACMode.HEAT
    
    @property
    def hvac_action(self):
        """Return the current running hvac operation."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF

        device = self._get_device()
        if device and device.get("state"):
            duty_cycle = device["state"].get("dutyCycle")
            if duty_cycle is None:
                return None
            # dutyCycle > 0 = la résistance chauffe
            return HVACAction.HEATING if duty_cycle > 0 else HVACAction.IDLE
        return None

    @property
    def preset_mode(self):
        """Return the current preset mode."""
        # Si un preset est en attente, l'afficher immédiatement
        if self._pending_preset_mode is not None:
            return self._pending_preset_mode
        
        device = self._get_device()
        if device and device.get("state"):
            mode = device["state"].get("targetMode", 1)
            # Mapping inverse selon ESPHome_GoodHome
            if mode in [9, 60]:  # Forcé confort ou Auto confort
                return PRESET_COMFORT
            elif mode in [2, 10, 30, 61]:  # Manuel éco, forcé éco, éco sur absence ou auto éco
                return PRESET_ECO
            elif mode == 5:  # Absence longue
                return PRESET_AWAY
            elif mode == 12:  # Absence courte
                return PRESET_SLEEP
            # Modes manuels et provisoires (0, 1, 3, 4, 8, 70) ou inconnus
        return PRESET_MANUAL
    
    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        device = self._get_device()
        if device and device.get("state"):
            state = device["state"]
            
            # Déterminer la plage de température pour couleur
            target_temp = state.get("targetTemp", 20)
            if target_temp <= 12.5:
                temp_range = "cold"  # Bleu
                temp_color = "#2196F3"
            elif target_temp <= 19.5:
                temp_range = "medium"  # Vert
                temp_color = "#4CAF50"
            else:
                temp_range = "hot"  # Rouge/Orange
                temp_color = "#FF5722"
            
            # Déterminer la raison du mode éco
            target_mode = state.get("targetMode", 0)
            eco_reason = None
            if target_mode == 2:
                eco_reason = "manual"  # Éco manuel
            elif target_mode == 30:
                eco_reason = "absence"  # Éco automatique après 20+ min sans présence
            elif target_mode == 61:
                eco_reason = "schedule"  # Éco selon planning auto
            
            return {
                "humidity": state.get("humidity"),
                "window_open": state.get("window", False),
                "occupancy": state.get("occupancyStatus", False),
                "duty_cycle": state.get("dutyCycle"),
                "eco_temperature": state.get("ecoTemp"),
                "comfort_temperature": state.get("comfTemp"),
                "antifreeze_temperature": state.get("antifTemp"),
                "override_temperature": state.get("overrideTemp"),
                "override_time": state.get("overrideTime"),
                "self_learning": state.get("selfLearning"),
                "self_learning_improve": state.get("selfLearningImprove"),
                "self_learning_days": state.get("selfLearningCountDay"),
                "eco_reason": eco_reason,  # Raison du mode éco (manual/absence/schedule)
                "firmware_version": state.get("fwVer"),
                "hardware_version": state.get("HwVer"),
                "code_name": state.get("codeName"),
                "room_name": state.get("roomName"),
                "window_timeout": state.get("windowTimeOut"),
                "fault_system": state.get("faultSystem"),
                "temperature_range": temp_range,
                "temperature_color": temp_color,
            }
        return {}
    
    async def async_set_temperature(self, **kwargs):
        """Set new target temperature with debounce."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            # Annuler la tâche de debounce précédente si elle existe
            if self._debounce_task is not None:
                self._debounce_task.cancel()
            
            # Stocker la température en attente
            self._pending_temperature = temperature
            
            # Mettre à jour l'affichage immédiatement avec la valeur locale
            self.async_write_ha_state()
            
            # Créer une nouvelle tâche de debounce
            self._debounce_task = self.hass.async_create_task(
                self._debounced_set_temperature()
            )
    
    async def _debounced_set_temperature(self):
        """Set temperature after debounce delay."""
        try:
            # Attendre le délai de debounce
            await asyncio.sleep(DEBOUNCE_DELAY)
            
            # Envoyer la requête
            if self._pending_temperature is not None:
                temp_to_set = self._pending_temperature
                _LOGGER.debug("Setting temperature to %s after debounce", temp_to_set)
                
                await self.hass.async_add_executor_job(
                    self._api.set_override_temperature, self._device_id, temp_to_set
                )
                
                # Fonction de vérification de la confirmation
                def check_temperature():
                    device = self._get_device()
                    if device and device.get("state"):
                        current_target = device["state"].get("targetTemp")
                        # Vérifier avec une tolérance de 0.1°C
                        if current_target is not None and abs(current_target - temp_to_set) < 0.1:
                            return True
                    return False
                
                # Attendre la confirmation du radiateur
                await self._wait_for_confirmation(check_temperature, f"Temperature {temp_to_set}°C")
                
                # Nettoyer l'état en attente
                self._pending_temperature = None
                self.async_write_ha_state()
                
        except asyncio.CancelledError:
            # La tâche a été annulée, ne rien faire
            _LOGGER.debug("Temperature set cancelled due to new change")
            pass
    
    async def async_set_hvac_mode(self, hvac_mode: HVACMode):
        """Set new target hvac mode."""
        # OFF = mode 3 (anti-gel manuel)
        # HEAT = mode 1 (manuel confort)
        if hvac_mode == HVACMode.OFF:
            mode = 3  # Manuel anti-gel
        else:
            mode = 1  # Manuel confort
        
        # État optimiste : afficher immédiatement le nouveau mode
        self._pending_hvac_mode = hvac_mode
        self.async_write_ha_state()
        
        # Envoyer la commande à l'API
        await self.hass.async_add_executor_job(
            self._api.set_mode, self._device_id, mode
        )
        
        # Fonction de vérification de la confirmation
        def check_hvac_mode():
            device = self._get_device()
            if device and device.get("state"):
                return device["state"].get("targetMode") == mode
            return False
        
        # Attendre la confirmation du radiateur
        await self._wait_for_confirmation(check_hvac_mode, f"HVAC mode {hvac_mode}")
        
        # Nettoyer l'état en attente
        self._pending_hvac_mode = None
        self.async_write_ha_state()
    
    async def async_set_preset_mode(self, preset_mode: str):
        """Set new preset mode."""
        # Mapping simplifié pour les presets courants
        # Pour un contrôle total, utiliser l'entité select.target_mode
        mode_map = {
            PRESET_COMFORT: 9,   # Forcé confort (retour auto)
            PRESET_ECO: 10,      # Forcé éco (retour auto)
            PRESET_MANUAL: 1,    # Manuel confort
            PRESET_AWAY: 5,      # Absence longue durée
            PRESET_SLEEP: 12,    # Absence courte durée
        }
        mode = mode_map.get(preset_mode, 1)
        
        # État optimiste : afficher immédiatement le nouveau preset
        self._pending_preset_mode = preset_mode
        self.async_write_ha_state()
        
        # Envoyer la commande à l'API
        await self.hass.async_add_executor_job(
            self._api.set_mode, self._device_id, mode
        )
        
        # Fonction de vérification de la confirmation
        def check_preset_mode():
            device = self._get_device()
            if device and device.get("state"):
                return device["state"].get("targetMode") == mode
            return False
        
        # Attendre la confirmation du radiateur
        await self._wait_for_confirmation(check_preset_mode, f"Preset mode {preset_mode}")
        
        # Nettoyer l'état en attente
        self._pending_preset_mode = None
        self.async_write_ha_state()
