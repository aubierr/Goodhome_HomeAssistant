"""Bouton d'identification des radiateurs GoodHome."""
from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .entity import GoodHomeEntity, async_add_new_devices
from .goodhome_api import GoodHomeError


async def async_setup_entry(hass, entry, async_add_entities):
    """Créer le bouton d'identification de chaque radiateur."""
    coordinator = entry.runtime_data.coordinator
    async_add_new_devices(
        entry,
        coordinator,
        lambda device_ids: [GoodHomeIdentifyButton(coordinator, device_id) for device_id in device_ids],
        async_add_entities,
    )


class GoodHomeIdentifyButton(GoodHomeEntity, ButtonEntity):
    """Fait biper le radiateur pour le localiser."""

    _attr_device_class = ButtonDeviceClass.IDENTIFY
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, device_id):
        """Initialiser le bouton."""
        super().__init__(coordinator, device_id, f"goodhome_{device_id}_identify")

    async def async_press(self) -> None:
        """Faire biper le radiateur."""
        try:
            await self.coordinator.client.async_identify(self._device_id)
        except GoodHomeError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
