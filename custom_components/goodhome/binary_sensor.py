"""Capteurs binaires GoodHome."""
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory

from .entity import GoodHomeEntity, async_add_new_devices


@dataclass(frozen=True, kw_only=True)
class GoodHomeBinarySensorDescription(BinarySensorEntityDescription):
    """Description d'un capteur binaire : valeur lue dans les données du radiateur."""

    value_fn: Callable[[dict, dict], bool]
    attributes_fn: Callable[[dict], dict] | None = None
    # La connectivité doit rester lisible quand le radiateur est déconnecté
    always_available: bool = False


BINARY_SENSORS = (
    GoodHomeBinarySensorDescription(
        key="connectivity",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        always_available=True,
        value_fn=lambda device, state: device.get("connected", False),
    ),
    GoodHomeBinarySensorDescription(
        key="self_learning_improve",
        translation_key="self_learning_improve",
        value_fn=lambda device, state: bool(state.get("selfLearningImprove", False)),
        attributes_fn=lambda state: {
            "self_learning_days": state.get("selfLearningCountDay"),
            "self_learning_enabled": state.get("selfLearning", False),
        },
    ),
    GoodHomeBinarySensorDescription(
        key="problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device, state: (state.get("faultSystem") or 0) != 0,
        attributes_fn=lambda state: {"fault_code": state.get("faultSystem")},
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Créer les capteurs binaires de chaque radiateur."""
    coordinator = entry.runtime_data.coordinator
    async_add_new_devices(
        entry,
        coordinator,
        lambda device_ids: [
            GoodHomeBinarySensor(coordinator, device_id, description)
            for device_id in device_ids
            for description in BINARY_SENSORS
        ],
        async_add_entities,
    )


class GoodHomeBinarySensor(GoodHomeEntity, BinarySensorEntity):
    """Capteur binaire d'un radiateur GoodHome."""

    entity_description: GoodHomeBinarySensorDescription

    def __init__(self, coordinator, device_id, description):
        """Initialiser le capteur binaire."""
        super().__init__(coordinator, device_id, f"goodhome_{device_id}_{description.key}")
        self.entity_description = description

    @property
    def available(self):
        """Disponibilité (la connectivité reste disponible tant que le radiateur existe)."""
        if self.entity_description.always_available:
            return self.coordinator.last_update_success and self.device is not None
        return super().available

    @property
    def is_on(self):
        """État du capteur binaire."""
        if self.device is None:
            return None
        return self.entity_description.value_fn(self.device, self.state_data)

    @property
    def extra_state_attributes(self):
        """Attributs du capteur binaire."""
        if self.entity_description.attributes_fn is None or self.device is None:
            return None
        return self.entity_description.attributes_fn(self.state_data)
