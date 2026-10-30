"""Températures de consigne GoodHome (confort, éco, hors-gel)."""
from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import UnitOfTemperature

from .entity import GoodHomeEntity, async_add_new_devices


@dataclass(frozen=True, kw_only=True)
class GoodHomeNumberDescription(NumberEntityDescription):
    """Description d'une température ; key est le paramètre de l'API."""

    description_text: str


NUMBERS = (
    GoodHomeNumberDescription(
        key="comfTemp",
        translation_key="comfort_temperature",
        icon="mdi:home-thermometer",
        description_text="Température de consigne en mode Confort",
    ),
    GoodHomeNumberDescription(
        key="ecoTemp",
        translation_key="eco_temperature",
        icon="mdi:leaf",
        description_text="Température de consigne en mode Économie d'énergie",
    ),
    GoodHomeNumberDescription(
        key="antifTemp",
        translation_key="antifreeze_temperature",
        icon="mdi:snowflake",
        description_text="Température de consigne en mode Hors-gel (OFF)",
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Créer les températures de consigne de chaque radiateur."""
    coordinator = entry.runtime_data.coordinator
    async_add_new_devices(
        entry,
        coordinator,
        lambda device_ids: [
            GoodHomeTemperatureNumber(coordinator, device_id, description)
            for device_id in device_ids
            for description in NUMBERS
        ],
        async_add_entities,
    )


class GoodHomeTemperatureNumber(GoodHomeEntity, NumberEntity):
    """Température de consigne d'un radiateur GoodHome."""

    entity_description: GoodHomeNumberDescription
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 7.0
    _attr_native_max_value = 30.0
    _attr_native_step = 0.5

    def __init__(self, coordinator, device_id, description):
        """Initialiser la température."""
        super().__init__(coordinator, device_id, f"goodhome_{device_id}_{description.key}")
        self.entity_description = description

    @property
    def native_value(self):
        """Température de consigne."""
        return self.state_data.get(self.entity_description.key)

    @property
    def extra_state_attributes(self):
        """Contexte de la consigne."""
        state = self.state_data
        return {
            "parameter": self.entity_description.key,
            "target_temp": state.get("targetTemp"),
            "current_temp": state.get("currentTemp"),
            "description": self.entity_description.description_text,
        }

    async def async_set_native_value(self, value: float) -> None:
        """Changer la consigne (l'API attend une décimale au plus)."""
        await self.async_send_state({self.entity_description.key: round(float(value), 1)})
