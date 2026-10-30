"""Tests des commandes : valeur envoyée, affichage immédiat et confirmation."""
from datetime import timedelta

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.goodhome.const import CONFIRMATION_TIMEOUT, DEBOUNCE_DELAY, DOMAIN

from .conftest import DEVICE_ID, SOCKETIO_URL, async_setup_entry_with, entity_id, sent_parameters

D = DEVICE_ID


def push(entry, **changes):
    """Simuler l'événement setState envoyé quand le radiateur a appliqué un réglage."""
    entry.runtime_data.coordinator.async_apply_push_event(
        "setState", {"objectType": "device", "objectId": DEVICE_ID, "data": changes}
    )


async def advance(hass, seconds):
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done()


async def test_preset_is_shown_until_confirmed(hass, setup_integration, mock_api):
    climate = entity_id(hass, "climate", f"goodhome_climate_{D}")
    await hass.services.async_call(
        "climate", "set_preset_mode", {"entity_id": climate, "preset_mode": "eco"}, blocking=True
    )
    assert sent_parameters(mock_api) == [{"targetMode": 10}]
    # Poignée de main Socket.io avant la commande
    assert any(str(call[1]).startswith(SOCKETIO_URL) for call in mock_api.mock_calls)
    # Affiché tout de suite, avant la confirmation du radiateur
    assert hass.states.get(climate).attributes["preset_mode"] == "eco"
    assert hass.states.get(climate).attributes["pending_confirmation"] == {"targetMode": 10}

    push(setup_integration, targetMode=10)
    await hass.async_block_till_done()
    assert hass.states.get(climate).attributes["preset_mode"] == "eco"
    assert "pending_confirmation" not in hass.states.get(climate).attributes

    # Confirmé : l'affichage suit de nouveau le radiateur
    push(setup_integration, targetMode=1)
    await hass.async_block_till_done()
    assert hass.states.get(climate).attributes["preset_mode"] == "manual"


async def test_unconfirmed_command_reverts_after_timeout(hass, setup_integration, mock_api):
    climate = entity_id(hass, "climate", f"goodhome_climate_{D}")
    await hass.services.async_call("climate", "turn_off", {"entity_id": climate}, blocking=True)
    assert sent_parameters(mock_api) == [{"targetMode": 3}]
    assert hass.states.get(climate).state == "off"

    await advance(hass, CONFIRMATION_TIMEOUT + 1)
    assert hass.states.get(climate).state == "auto"


async def test_temperature_is_debounced(hass, setup_integration, mock_api):
    climate = entity_id(hass, "climate", f"goodhome_climate_{D}")
    for temperature in (19.5, 20, 20.5):
        await hass.services.async_call(
            "climate", "set_temperature", {"entity_id": climate, "temperature": temperature}, blocking=True
        )
    assert hass.states.get(climate).attributes["temperature"] == 20.5
    assert sent_parameters(mock_api) == []

    await advance(hass, DEBOUNCE_DELAY + 1)
    # Une seule commande, avec la dernière consigne
    assert sent_parameters(mock_api) == [{"overrideTemp": 20.5, "targetMode": 8}]

    push(setup_integration, overrideTemp=20.5, targetTemp=20.5, targetMode=8)
    await hass.async_block_till_done()
    assert hass.states.get(climate).attributes["temperature"] == 20.5


async def test_failed_command_raises_and_reverts(hass, config_entry, aioclient_mock):
    await async_setup_entry_with(hass, config_entry, aioclient_mock, command_status=500)

    switch = entity_id(hass, "switch", f"goodhome_{D}_selfLearning")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
    assert hass.states.get(switch).state == "off"


async def test_switch_turn_on(hass, setup_integration, mock_api):
    switch = entity_id(hass, "switch", f"goodhome_{D}_selfLearning")
    await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
    assert sent_parameters(mock_api) == [{"selfLearning": True}]
    assert hass.states.get(switch).state == "on"


async def test_number_set_value(hass, setup_integration, mock_api):
    number = entity_id(hass, "number", f"goodhome_{D}_comfTemp")
    await hass.services.async_call("number", "set_value", {"entity_id": number, "value": 20.5}, blocking=True)
    assert sent_parameters(mock_api) == [{"comfTemp": 20.5}]
    assert hass.states.get(number).state == "20.5"


async def test_select_option(hass, setup_integration, mock_api):
    select = entity_id(hass, "select", f"goodhome_target_mode_{D}")
    await hass.services.async_call(
        "select", "select_option", {"entity_id": select, "option": "temporary_override"}, blocking=True
    )
    assert sent_parameters(mock_api) == [{"targetMode": 4}]
    assert hass.states.get(select).state == "temporary_override"


async def test_select_read_only_mode_is_refused(hass, setup_integration, mock_api):
    select = entity_id(hass, "select", f"goodhome_target_mode_{D}")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "select", "select_option", {"entity_id": select, "option": "eco_auto_absence"}, blocking=True
        )
    assert sent_parameters(mock_api) == []


async def test_identify_button_and_service(hass, setup_integration, mock_api):
    button = entity_id(hass, "button", f"goodhome_{D}_identify")
    await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
    # Identifiant GoodHome (anciennes automatisations), puis appareil Home Assistant (sélecteur)
    await hass.services.async_call(DOMAIN, "identify_device", {"device_id": DEVICE_ID}, blocking=True)
    device = dr.async_entries_for_config_entry(dr.async_get(hass), setup_integration.entry_id)[0]
    await hass.services.async_call(DOMAIN, "identify_device", {"device_id": device.id}, blocking=True)
    assert sent_parameters(mock_api) == [{"ping": 1}, {"ping": 1}, {"ping": 1}]

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(DOMAIN, "identify_device", {"device_id": "unknown"}, blocking=True)


async def test_auto_mode_is_confirmed_by_schedule_choice(hass, setup_integration, mock_api, caplog):
    """Envoyer « Auto Éco » en période de confort : le radiateur passe en Auto Confort."""
    select = entity_id(hass, "select", f"goodhome_target_mode_{D}")
    push(setup_integration, targetMode=8)
    await hass.async_block_till_done()

    await hass.services.async_call(
        "select", "select_option", {"entity_id": select, "option": "auto_eco"}, blocking=True
    )
    assert sent_parameters(mock_api) == [{"targetMode": 61}]
    assert hass.states.get(select).state == "auto_eco"

    # Le planning choisit le confort : la commande est confirmée, sans avertissement
    push(setup_integration, targetMode=60)
    await hass.async_block_till_done()
    assert hass.states.get(select).state == "auto_comfort"

    await advance(hass, CONFIRMATION_TIMEOUT + 1)
    assert hass.states.get(select).state == "auto_comfort"
    assert "not confirmed" not in caplog.text


async def test_auto_mode_follows_the_schedule(hass, config_entry, aioclient_mock, caplog):
    await async_setup_entry_with(hass, config_entry, aioclient_mock, targetMode=8)
    climate = entity_id(hass, "climate", f"goodhome_climate_{D}")
    assert hass.states.get(climate).state == "heat"

    await hass.services.async_call(
        "climate", "set_hvac_mode", {"entity_id": climate, "hvac_mode": "auto"}, blocking=True
    )
    assert sent_parameters(aioclient_mock) == [{"targetMode": 60}]
    assert hass.states.get(climate).state == "auto"

    # Le planning choisit l'éco : la commande est quand même confirmée
    push(config_entry, targetMode=61)
    await hass.async_block_till_done()
    assert hass.states.get(climate).state == "auto"
    assert "pending_confirmation" not in hass.states.get(climate).attributes

    await advance(hass, CONFIRMATION_TIMEOUT + 1)
    assert "not confirmed" not in caplog.text


@pytest.mark.parametrize(
    ("mode_before", "turn_on_mode"),
    [
        (60, 60),  # Planning : retour au planning
        (10, 60),  # Forçage du planning : retour au planning
        (8, 8),  # Consigne manuelle : la même, sans perdre overrideTemp
        (2, 2),  # Manuel éco
        (12, 1),  # Absence courte (provisoire) : confort manuel
    ],
)
async def test_turn_on_restores_mode_before_turn_off(hass, config_entry, aioclient_mock, mode_before, turn_on_mode):
    await async_setup_entry_with(hass, config_entry, aioclient_mock, targetMode=mode_before)
    climate = entity_id(hass, "climate", f"goodhome_climate_{D}")

    await hass.services.async_call("climate", "turn_off", {"entity_id": climate}, blocking=True)
    push(config_entry, targetMode=3)
    await hass.async_block_till_done()
    await hass.services.async_call("climate", "turn_on", {"entity_id": climate}, blocking=True)

    assert sent_parameters(aioclient_mock) == [{"targetMode": 3}, {"targetMode": turn_on_mode}]


async def test_turn_on_without_known_mode_heats(hass, config_entry, aioclient_mock):
    """Arrêté avant le démarrage de Home Assistant : confort manuel, comme avant."""
    await async_setup_entry_with(hass, config_entry, aioclient_mock, targetMode=3)
    climate = entity_id(hass, "climate", f"goodhome_climate_{D}")

    await hass.services.async_call("climate", "turn_on", {"entity_id": climate}, blocking=True)
    assert sent_parameters(aioclient_mock) == [{"targetMode": 1}]


async def test_turn_on_when_already_on_sends_nothing(hass, setup_integration, mock_api):
    climate = entity_id(hass, "climate", f"goodhome_climate_{D}")
    await hass.services.async_call("climate", "turn_on", {"entity_id": climate}, blocking=True)
    assert sent_parameters(mock_api) == []


async def test_switch_shows_pending_value(hass, setup_integration, mock_api):
    switch = entity_id(hass, "switch", f"goodhome_{D}_selfLearning")
    await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
    assert hass.states.get(switch).attributes["pending_confirmation"] == {"selfLearning": True}
