"""Interrupteurs GoodHome (réglages booléens du radiateur)."""
from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory

from .entity import GoodHomeEntity, async_add_new_devices


@dataclass(frozen=True, kw_only=True)
class GoodHomeSwitchDescription(SwitchEntityDescription):
    """Description d'un interrupteur ; key est le paramètre de l'API."""

    description_text: str


SWITCHES = (
    GoodHomeSwitchDescription(
        key="window",
        translation_key="window",
        description_text="Enable/disable automatic open window detection based on temperature drop",
    ),
    GoodHomeSwitchDescription(
        key="occupancyStatus",
        translation_key="occupancy_status",
        description_text="Enable/disable occupancy consideration for heating control",
    ),
    GoodHomeSwitchDescription(
        key="selfLearning",
        translation_key="self_learning",
        description_text="Enable/disable auto-learning mode (requires occupancyStatus enabled)",
    ),
    GoodHomeSwitchDescription(
        key="noprog",
        translation_key="manual_mode",
        description_text="Manual mode (on) or Auto mode with scheduling (off)",
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Créer les interrupteurs de chaque radiateur."""
    coordinator = entry.runtime_data.coordinator
    async_add_new_devices(
        entry,
        coordinator,
        lambda device_ids: [
            GoodHomeSwitch(coordinator, device_id, description)
            for device_id in device_ids
            for description in SWITCHES
        ],
        async_add_entities,
    )


class GoodHomeSwitch(GoodHomeEntity, SwitchEntity):
    """Réglage booléen d'un radiateur GoodHome."""

    entity_description: GoodHomeSwitchDescription
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, device_id, description):
        """Initialiser l'interrupteur."""
        super().__init__(coordinator, device_id, f"goodhome_{device_id}_{description.key}")
        self.entity_description = description

    @property
    def is_on(self):
        """État du réglage (l'API peut renvoyer un booléen, 0/1 ou du texte)."""
        value = self.state_data.get(self.entity_description.key)
        if isinstance(value, str):
            return value.lower() in ("1", "true")
        return None if value is None else bool(value)

    @property
    def extra_state_attributes(self):
        """Description du réglage, et délai pour la détection de fenêtre."""
        attrs = {"description": self.entity_description.description_text}
        if self.entity_description.key == "window":
            attrs["window_timeout_minutes"] = self.state_data.get("windowTimeOut")
        return self._with_pending(attrs)

    async def async_turn_on(self, **kwargs):
        """Activer le réglage."""
        await self.async_send_state({self.entity_description.key: True})

    async def async_turn_off(self, **kwargs):
        """Désactiver le réglage."""
        await self.async_send_state({self.entity_description.key: False})
