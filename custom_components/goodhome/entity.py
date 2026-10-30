"""Entité de base des radiateurs GoodHome."""
import logging

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GoodHomeCoordinator
from .goodhome_api import GoodHomeError

_LOGGER = logging.getLogger(__name__)


def _as_str(value):
    """Convertir une version en texte (l'API peut renvoyer des nombres)."""
    return str(value) if value is not None else None


def _same_value(actual, expected):
    """Comparer une valeur de l'API à la valeur envoyée (tolérance pour les températures)."""
    if isinstance(expected, float) or isinstance(actual, float):
        try:
            return abs(float(actual) - float(expected)) < 0.05
        except (TypeError, ValueError):
            return False
    return actual == expected


def async_add_new_devices(entry, coordinator, build_entities, async_add_entities):
    """Ajouter les entités des radiateurs présents, puis de ceux qui apparaissent ensuite.

    Un radiateur ajouté dans l'app GoodHome apparaît à la mise à jour suivante
    du coordinator, sans redémarrer Home Assistant.
    """
    known_ids = set()

    @callback
    def _add_new_devices():
        new_ids = [device_id for device_id in coordinator.data or {} if device_id not in known_ids]
        if not new_ids:
            return
        known_ids.update(new_ids)
        async_add_entities(build_entities(new_ids))

    _add_new_devices()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_devices))


class GoodHomeEntity(CoordinatorEntity[GoodHomeCoordinator]):
    """Entité rattachée à un radiateur.

    Les commandes passent par async_send_state : les valeurs envoyées s'affichent
    tout de suite (état optimiste) jusqu'à ce que le radiateur les confirme.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: GoodHomeCoordinator, device_id: str, unique_id: str):
        """Initialiser l'entité."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = unique_id
        self._pending = {}  # Champs de « state » envoyés mais pas encore confirmés

    @property
    def device(self):
        """Données du radiateur, None s'il a disparu du compte."""
        return (self.coordinator.data or {}).get(self._device_id)

    @property
    def state_data(self):
        """Champs « state » du radiateur, avec les valeurs en attente de confirmation."""
        device = self.device
        return {**(device["state"] if device else {}), **self._pending}

    @property
    def available(self):
        """Disponible si le radiateur existe et est connecté au cloud."""
        device = self.device
        return super().available and device is not None and device.get("connected", False)

    @property
    def device_info(self):
        """Appareil Home Assistant du radiateur."""
        device = self.device or {}
        state = device.get("state") or {}
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device.get("name"),
            manufacturer="GoodHome",
            model=state.get("codeName") or "Thermostat",
            sw_version=_as_str(state.get("fwVer")),
            hw_version=_as_str(state.get("HwVer")),
        )

    async def async_send_state(self, parameters, display=None):
        """Envoyer des paramètres au radiateur.

        L'action se termine dès l'envoi (une erreur est remontée tout de suite) ;
        la confirmation, qui prend 45 s à 2 min, est attendue en tâche de fond.
        display : champs à afficher en plus pendant l'attente (ex. targetTemp, que
        le radiateur déduit de overrideTemp) ; seuls les paramètres sont vérifiés.
        """
        shown = {**parameters, **(display or {})}
        self._pending.update(shown)
        self.async_write_ha_state()
        try:
            await self.coordinator.client.async_set_state(self._device_id, parameters)
        except GoodHomeError as err:
            self._clear_pending(shown)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err

        self.coordinator.config_entry.async_create_background_task(
            self.hass, self._async_wait_confirmation(parameters, shown), f"goodhome confirm {self.entity_id}"
        )

    async def _async_wait_confirmation(self, parameters, shown):
        def _confirmed():
            state = (self.device or {}).get("state") or {}
            return all(_same_value(state.get(key), value) for key, value in parameters.items())

        try:
            await self.coordinator.async_wait_for(_confirmed, f"{self.entity_id} {parameters}")
        finally:
            self._clear_pending(shown)

    def _clear_pending(self, shown):
        # Une commande plus récente sur le même champ garde sa propre valeur en attente
        for key, value in shown.items():
            if self._pending.get(key) == value:
                del self._pending[key]
        if self.hass is not None:
            self.async_write_ha_state()
