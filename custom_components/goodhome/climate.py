"""Thermostat GoodHome."""
import asyncio
import logging

from homeassistant.components.climate import (
    PRESET_AWAY,
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_SLEEP,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError

from .const import DEBOUNCE_DELAY
from .entity import GoodHomeEntity, async_add_new_devices

_LOGGER = logging.getLogger(__name__)

PRESET_MANUAL = "manual"

# Mode envoyé pour chaque preset (pour un contrôle total, utiliser select.target_mode)
PRESET_TO_MODE = {
    PRESET_COMFORT: 9,   # Forcé confort (retour auto)
    PRESET_ECO: 10,      # Forcé éco (retour auto)
    PRESET_MANUAL: 1,    # Manuel confort
    PRESET_AWAY: 5,      # Absence longue durée
    PRESET_SLEEP: 12,    # Absence courte durée
}
# Lecture, selon ESPHome_GoodHome ; les autres modes (0, 1, 3, 4, 8, 70, inconnus) donnent « manual »
MODE_TO_PRESET = {
    9: PRESET_COMFORT,   # Forcé confort
    60: PRESET_COMFORT,  # Auto confort
    2: PRESET_ECO,       # Manuel éco
    10: PRESET_ECO,      # Forcé éco
    30: PRESET_ECO,      # Éco sur absence détectée
    61: PRESET_ECO,      # Auto éco
    5: PRESET_AWAY,      # Absence longue
    12: PRESET_SLEEP,    # Absence courte
}
MODE_OFF = 3  # Manuel hors-gel : seul mode d'arrêt, comme ESPHome_GoodHome
MODE_HEAT = 1  # Manuel confort
MODE_OVERRIDE = 8  # Manuel override : le radiateur garde overrideTemp

# Raison d'un mode éco, exposée dans l'attribut eco_reason
ECO_REASONS = {2: "manual", 30: "absence", 61: "schedule"}


async def async_setup_entry(hass, entry, async_add_entities):
    """Créer le thermostat de chaque radiateur."""
    coordinator = entry.runtime_data.coordinator
    async_add_new_devices(
        entry,
        coordinator,
        lambda device_ids: [GoodHomeClimate(coordinator, device_id) for device_id in device_ids],
        async_add_entities,
    )


class GoodHomeClimate(GoodHomeEntity, ClimateEntity):
    """Thermostat d'un radiateur GoodHome."""

    # Entité principale de l'appareil : elle porte le nom de l'appareil
    _attr_name = None
    # Traductions du preset « manual » et des attributs (eco_reason, temperature_range...)
    _attr_translation_key = "radiator"
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

    def __init__(self, coordinator, device_id):
        """Initialiser le thermostat."""
        super().__init__(coordinator, device_id, f"goodhome_climate_{device_id}")
        self._debounce_task = None

    @property
    def current_temperature(self):
        """Température ambiante."""
        return self.state_data.get("currentTemp")

    @property
    def current_humidity(self):
        """Humidité ambiante."""
        return self.state_data.get("humidity")

    @property
    def target_temperature(self):
        """Température de consigne."""
        return self.state_data.get("targetTemp")

    @property
    def hvac_mode(self):
        """Arrêt en hors-gel manuel, chauffe sinon."""
        return HVACMode.OFF if self.state_data.get("targetMode") == MODE_OFF else HVACMode.HEAT

    @property
    def hvac_action(self):
        """Chauffe tant que la part de chauffe (dutyCycle) est positive."""
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        duty_cycle = self.state_data.get("dutyCycle")
        if duty_cycle is None:
            return None
        return HVACAction.HEATING if duty_cycle > 0 else HVACAction.IDLE

    @property
    def preset_mode(self):
        """Preset correspondant au mode du radiateur."""
        return MODE_TO_PRESET.get(self.state_data.get("targetMode"), PRESET_MANUAL)

    @property
    def extra_state_attributes(self):
        """Réglages et informations du radiateur."""
        state = self.state_data
        target_temp = state.get("targetTemp") or 20
        # Plage de consigne, pour colorer les cartes du tableau de bord
        if target_temp <= 12.5:
            temp_range, temp_color = "cold", "#2196F3"
        elif target_temp <= 19.5:
            temp_range, temp_color = "medium", "#4CAF50"
        else:
            temp_range, temp_color = "hot", "#FF5722"

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
            "eco_reason": ECO_REASONS.get(state.get("targetMode")),
            "firmware_version": state.get("fwVer"),
            "hardware_version": state.get("HwVer"),
            "code_name": state.get("codeName"),
            "room_name": state.get("roomName"),
            "window_timeout": state.get("windowTimeOut"),
            "fault_system": state.get("faultSystem"),
            "temperature_range": temp_range,
            "temperature_color": temp_color,
        }

    async def async_set_temperature(self, **kwargs):
        """Changer la consigne, envoyée après DEBOUNCE_DELAY sans nouveau changement."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        if self._debounce_task is not None:
            self._debounce_task.cancel()
        # Afficher la nouvelle consigne tout de suite
        self._pending["targetTemp"] = temperature
        self.async_write_ha_state()
        self._debounce_task = self.coordinator.config_entry.async_create_background_task(
            self.hass, self._async_send_temperature(temperature), f"goodhome temperature {self.entity_id}"
        )

    async def _async_send_temperature(self, temperature):
        try:
            await asyncio.sleep(DEBOUNCE_DELAY)
        except asyncio.CancelledError:
            # Remplacée par une consigne plus récente
            return
        try:
            await self.async_send_state(
                {"overrideTemp": temperature, "targetMode": MODE_OVERRIDE}, display={"targetTemp": temperature}
            )
        except HomeAssistantError as err:
            # Action déjà terminée (anti-rebond) : l'erreur ne peut qu'être journalisée
            _LOGGER.error("Could not set %s to %s°C: %s", self.entity_id, temperature, err)
            self._pending.pop("targetTemp", None)
            self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode):
        """Arrêter (hors-gel manuel) ou chauffer (confort manuel)."""
        await self.async_send_state({"targetMode": MODE_OFF if hvac_mode == HVACMode.OFF else MODE_HEAT})

    async def async_turn_on(self):
        """Chauffer (confort manuel)."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self):
        """Arrêter (hors-gel manuel)."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_preset_mode(self, preset_mode: str):
        """Appliquer un preset."""
        await self.async_send_state({"targetMode": PRESET_TO_MODE.get(preset_mode, MODE_HEAT)})
