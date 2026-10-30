"""Tests des entités : valeurs lues et identifiants conservés depuis la v1."""
import pytest
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN, EntityCategory
from homeassistant.helpers import entity_registry as er

from .conftest import DEVICE_ID, async_setup_entry_with, entity_id

D = DEVICE_ID


@pytest.mark.parametrize(
    ("platform", "unique_id", "expected"),
    [
        ("climate", f"goodhome_climate_{D}", "auto"),
        ("sensor", f"goodhome_{D}_temperature", "19.6"),
        ("sensor", f"goodhome_{D}_target_temperature", "19"),
        ("sensor", f"goodhome_{D}_humidity", "58.2"),
        ("sensor", f"goodhome_{D}_duty_cycle", "40"),
        # 40 % de 1000 W (DLRIRDH1000)
        ("sensor", f"goodhome_{D}_power_consumption", "400.0"),
        ("sensor", f"goodhome_{D}_self_learning_days", "0"),
        ("sensor", f"goodhome_{D}_device_info", "FW: 01206.3 TO100 | HW: 0001"),
        ("binary_sensor", f"goodhome_{D}_connectivity", STATE_ON),
        ("binary_sensor", f"goodhome_{D}_problem", STATE_OFF),
        ("binary_sensor", f"goodhome_{D}_self_learning_improve", STATE_OFF),
        ("switch", f"goodhome_{D}_window", STATE_ON),
        ("switch", f"goodhome_{D}_occupancyStatus", STATE_ON),
        ("switch", f"goodhome_{D}_selfLearning", STATE_OFF),
        ("switch", f"goodhome_{D}_noprog", STATE_OFF),
        ("number", f"goodhome_{D}_comfTemp", "19"),
        ("number", f"goodhome_{D}_ecoTemp", "16"),
        ("number", f"goodhome_{D}_antifTemp", "7"),
        ("select", f"goodhome_target_mode_{D}", "auto_comfort"),
        ("button", f"goodhome_{D}_identify", STATE_UNKNOWN),
    ],
)
async def test_entity_states(hass, setup_integration, platform, unique_id, expected):
    assert hass.states.get(entity_id(hass, platform, unique_id)).state == expected


async def test_climate_attributes(hass, setup_integration):
    state = hass.states.get(entity_id(hass, "climate", f"goodhome_climate_{D}"))
    assert state.attributes["current_temperature"] == 19.6
    assert state.attributes["temperature"] == 19
    assert state.attributes["preset_mode"] == "comfort"
    assert state.attributes["hvac_action"] == "heating"
    assert state.attributes["eco_reason"] is None
    assert state.attributes["target_mode_value"] == 60
    # Rien en attente de confirmation
    assert "pending_confirmation" not in state.attributes


async def test_duplicate_temperature_sensors_disabled_by_default(hass, setup_integration):
    registry = er.async_get(hass)
    entry = registry.async_get(entity_id(hass, "sensor", f"goodhome_{D}_comfort_temp"))
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION


@pytest.mark.parametrize(
    ("target_mode", "hvac_mode", "preset"),
    [
        (0, "heat", "manual"),
        (1, "heat", "manual"),
        (2, "heat", "eco"),
        (3, "off", "manual"),
        (5, "heat", "away"),
        (8, "heat", "manual"),
        (12, "heat", "sleep"),
        # Planning actif : automatique, y compris pendant un forçage (9, 10)
        (9, "auto", "comfort"),
        (10, "auto", "eco"),
        (30, "auto", "eco"),
        (60, "auto", "comfort"),
        (61, "auto", "eco"),
        (99, "heat", "manual"),
    ],
)
async def test_climate_mode_mapping(hass, config_entry, aioclient_mock, target_mode, hvac_mode, preset):
    await async_setup_entry_with(hass, config_entry, aioclient_mock, targetMode=target_mode)

    state = hass.states.get(entity_id(hass, "climate", f"goodhome_climate_{D}"))
    assert state.state == hvac_mode
    assert state.attributes["preset_mode"] == preset


async def test_unknown_mode_is_unknown_in_select(hass, config_entry, aioclient_mock):
    await async_setup_entry_with(hass, config_entry, aioclient_mock, targetMode=99)

    state = hass.states.get(entity_id(hass, "select", f"goodhome_target_mode_{D}"))
    assert state.state == STATE_UNKNOWN
    assert state.attributes["target_mode_value"] == 99


async def test_disconnected_device_is_unavailable(hass, config_entry, aioclient_mock):
    await async_setup_entry_with(hass, config_entry, aioclient_mock, connected=False)

    assert hass.states.get(entity_id(hass, "climate", f"goodhome_climate_{D}")).state == STATE_UNAVAILABLE
    # La connectivité reste lisible pour montrer la déconnexion
    assert hass.states.get(entity_id(hass, "binary_sensor", f"goodhome_{D}_connectivity")).state == STATE_OFF


async def test_device_info_shows_unused_api_fields(hass, config_entry, aioclient_mock):
    """Un champ de l'API qu'aucune entité n'exploite reste visible pour le débogage."""
    await async_setup_entry_with(hass, config_entry, aioclient_mock, holidayTimeout=1767225600)

    attributes = hass.states.get(entity_id(hass, "sensor", f"goodhome_{D}_device_info")).attributes
    assert attributes["other_fields"] == {"holidayTimeout": 1767225600}


async def test_known_api_fields_are_not_repeated(hass, setup_integration):
    attributes = hass.states.get(entity_id(hass, "sensor", f"goodhome_{D}_device_info")).attributes
    # Tous les champs du radiateur réel sont exploités ; userHash reste masqué
    assert attributes["other_fields"] == {}


@pytest.mark.parametrize(
    ("platform", "unique_id"),
    [("switch", f"goodhome_{D}_window"), ("switch", f"goodhome_{D}_noprog"), ("number", f"goodhome_{D}_comfTemp")],
)
async def test_settings_are_configuration_entities(hass, setup_integration, platform, unique_id):
    entry = er.async_get(hass).async_get(entity_id(hass, platform, unique_id))
    assert entry.entity_category is EntityCategory.CONFIG
