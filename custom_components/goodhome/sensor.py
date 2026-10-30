"""Capteurs GoodHome."""
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfPower, UnitOfTemperature, UnitOfTime

from .entity import GoodHomeEntity, async_add_new_devices


def rated_power(state):
    """Puissance nominale déduite du modèle (ex. DLRIRFH1800 -> 1800 W)."""
    match = re.search(r"(\d+)$", state.get("codeName") or "")
    return int(match.group(1)) if match else None


def power_consumption(state):
    """Puissance consommée : part de chauffe (%) × puissance nominale."""
    power, duty_cycle = rated_power(state), state.get("dutyCycle")
    if power is None or duty_cycle is None:
        return None
    return round(duty_cycle / 100 * power, 1)


@dataclass(frozen=True, kw_only=True)
class GoodHomeSensorDescription(SensorEntityDescription):
    """Description d'un capteur : valeur lue dans le « state » du radiateur."""

    value_fn: Callable[[dict], Any]
    attributes_fn: Callable[[dict, dict], dict] | None = None


def _device_info_attributes(device, state):
    return {
        "device_type": device.get("type"),
        "power_watts": rated_power(state),
        "firmware_version": state.get("fwVer"),
        "hardware_version": state.get("HwVer"),
        "code_name": state.get("codeName"),
        "room_name": state.get("roomName"),
        "fault_system": state.get("faultSystem"),
        "window_timeout": state.get("windowTimeOut"),
        "override_time": state.get("overrideTime"),
        "self_learning_days": state.get("selfLearningCountDay"),
        "connected": device.get("connected", False),
        "device_id": device.get("id"),
    }


SENSORS = (
    GoodHomeSensorDescription(
        key="temperature",
        translation_key="current_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: state.get("currentTemp"),
    ),
    GoodHomeSensorDescription(
        key="target_temperature",
        translation_key="target_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda state: state.get("targetTemp"),
    ),
    GoodHomeSensorDescription(
        key="humidity",
        translation_key="humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: state.get("humidity"),
    ),
    # Doublons des entités number : désactivés par défaut pour les nouvelles installations
    GoodHomeSensorDescription(
        key="comfort_temp",
        translation_key="comfort_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_registry_enabled_default=False,
        value_fn=lambda state: state.get("comfTemp"),
    ),
    GoodHomeSensorDescription(
        key="eco_temp",
        translation_key="eco_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_registry_enabled_default=False,
        value_fn=lambda state: state.get("ecoTemp"),
    ),
    GoodHomeSensorDescription(
        key="antifreeze_temp",
        translation_key="antifreeze_temp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_registry_enabled_default=False,
        value_fn=lambda state: state.get("antifTemp"),
    ),
    GoodHomeSensorDescription(
        key="duty_cycle",
        translation_key="duty_cycle",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: state.get("dutyCycle"),
    ),
    GoodHomeSensorDescription(
        key="power_consumption",
        translation_key="power_consumption",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=power_consumption,
    ),
    GoodHomeSensorDescription(
        key="device_info",
        translation_key="device_info",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: f"FW: {state.get('fwVer', 'Unknown')} | HW: {state.get('HwVer', 'Unknown')}",
        attributes_fn=_device_info_attributes,
    ),
    GoodHomeSensorDescription(
        key="self_learning_days",
        translation_key="self_learning_days",
        native_unit_of_measurement=UnitOfTime.DAYS,
        value_fn=lambda state: state.get("selfLearningCountDay"),
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Créer les capteurs de chaque radiateur."""
    coordinator = entry.runtime_data.coordinator
    async_add_new_devices(
        entry,
        coordinator,
        lambda device_ids: [
            GoodHomeSensor(coordinator, device_id, description)
            for device_id in device_ids
            for description in SENSORS
        ],
        async_add_entities,
    )


class GoodHomeSensor(GoodHomeEntity, SensorEntity):
    """Capteur d'un radiateur GoodHome."""

    entity_description: GoodHomeSensorDescription

    def __init__(self, coordinator, device_id, description):
        """Initialiser le capteur."""
        super().__init__(coordinator, device_id, f"goodhome_{device_id}_{description.key}")
        self.entity_description = description

    @property
    def native_value(self):
        """Valeur du capteur."""
        return self.entity_description.value_fn(self.state_data)

    @property
    def extra_state_attributes(self):
        """Attributs du capteur (seulement pour les informations de l'appareil)."""
        if self.entity_description.attributes_fn is None or self.device is None:
            return None
        return self.entity_description.attributes_fn(self.device, self.state_data)
