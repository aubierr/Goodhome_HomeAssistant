"""Sélection du mode de fonctionnement (targetMode) des radiateurs GoodHome."""
from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN
from .entity import GoodHomeEntity, async_add_new_devices, is_auto_mode

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

# Envoyer 60 ou 61 passe le radiateur en automatique : confirmé par n'importe quel mode auto
AUTO_OPTIONS = {"auto_comfort", "auto_eco"}

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


async def async_setup_entry(hass, entry, async_add_entities):
    """Créer la sélection de mode de chaque radiateur."""
    coordinator = entry.runtime_data.coordinator
    async_add_new_devices(
        entry,
        coordinator,
        lambda device_ids: [GoodHomeTargetModeSelect(coordinator, device_id) for device_id in device_ids],
        async_add_entities,
    )


class GoodHomeTargetModeSelect(GoodHomeEntity, SelectEntity):
    """Mode de fonctionnement d'un radiateur GoodHome."""

    _attr_translation_key = "target_mode"
    _attr_options = TARGET_MODE_OPTIONS

    def __init__(self, coordinator, device_id):
        """Initialiser la sélection."""
        super().__init__(coordinator, device_id, f"goodhome_target_mode_{device_id}")

    @property
    def current_option(self):
        """Mode actuel ; une valeur inconnue donne l'état « inconnu »
        (la valeur brute reste visible dans l'attribut target_mode_value)."""
        return TARGET_MODES_REVERSE.get(self.state_data.get("targetMode"))

    async def async_select_option(self, option: str) -> None:
        """Changer de mode."""
        if option in READ_ONLY_MODES:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="read_only_mode",
                translation_placeholders={"option": option},
            )
        await self.async_send_state(
            {"targetMode": TARGET_MODES[option]},
            confirmed=is_auto_mode if option in AUTO_OPTIONS else None,
        )

    @property
    def extra_state_attributes(self):
        """Valeur brute du mode et réglages associés."""
        state = self.state_data
        return self._with_pending({
            "target_mode_value": state.get("targetMode"),
            "target_temp": state.get("targetTemp"),
            "eco_temp": state.get("ecoTemp"),
            "comfort_temp": state.get("comfTemp"),
            "antifreeze_temp": state.get("antifTemp"),
            "override_temp": state.get("overrideTemp"),
            "manual_mode": state.get("noprog"),
            "self_learning": state.get("selfLearning"),
            "occupancy_status": state.get("occupancyStatus"),
        })
