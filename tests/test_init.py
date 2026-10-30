"""Tests du chargement du compte."""
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.setup import async_setup_component

from custom_components.goodhome import async_remove_config_entry_device
from custom_components.goodhome.const import DOMAIN

from .conftest import DEVICE_ID, DEVICES_URL, LOGIN_URL


def _device(hass, entry, device_id):
    """Appareil du compte (async_get_device est refusé depuis Home Assistant 2026)."""
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    return next(device for device in devices if (DOMAIN, device_id) in device.identifiers)


async def test_setup_and_unload(hass, setup_integration, no_push):
    assert setup_integration.state is ConfigEntryState.LOADED
    # L'écoute temps réel est lancée au chargement
    no_push.assert_called_once()

    device = _device(hass, setup_integration, DEVICE_ID)
    assert device.name == "CUISINE"
    assert device.model == "DLRIRDH1000"
    assert device.sw_version == "01206.3 TO100"

    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    assert setup_integration.state is ConfigEntryState.NOT_LOADED


async def test_invalid_credentials_start_reauth(hass, config_entry, aioclient_mock):
    aioclient_mock.post(LOGIN_URL, status=401)
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]


async def test_cloud_unreachable_retries(hass, config_entry, aioclient_mock):
    aioclient_mock.post(LOGIN_URL, status=503)
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_devices_unreachable_retries(hass, config_entry, aioclient_mock):
    aioclient_mock.post(LOGIN_URL, json={"token": "t", "id": "user-1"})
    aioclient_mock.get(DEVICES_URL, status=500)
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_yaml_is_imported(hass, mock_api):
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {"email": "a@b.c", "password": "p"}})
    await hass.async_block_till_done()

    entries = hass.config_entries.async_entries(DOMAIN)
    assert [entry.unique_id for entry in entries] == ["a@b.c"]
    assert ir.async_get(hass).async_get_issue(HOMEASSISTANT_DOMAIN, f"deprecated_yaml_{DOMAIN}")


async def test_removed_device_can_be_deleted(hass, setup_integration):
    device_registry = dr.async_get(hass)
    stale = device_registry.async_get_or_create(
        config_entry_id=setup_integration.entry_id, identifiers={(DOMAIN, "removed")}
    )
    current = _device(hass, setup_integration, DEVICE_ID)

    assert await async_remove_config_entry_device(hass, setup_integration, stale)
    assert not await async_remove_config_entry_device(hass, setup_integration, current)
