"""Tests de la configuration depuis l'interface."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.goodhome.const import DOMAIN

from .conftest import EMAIL, LOGIN_URL, PASSWORD, USER_ID


@pytest.fixture
def mock_setup_entry():
    """Ne pas charger le compte créé : seul le flow est testé ici."""
    with patch("custom_components.goodhome.async_setup_entry", new=AsyncMock(return_value=True)) as setup:
        yield setup


async def test_user_flow_creates_entry(hass, aioclient_mock, mock_setup_entry):
    aioclient_mock.post(LOGIN_URL, json={"token": "t", "id": USER_ID})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"email": EMAIL, "password": PASSWORD}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"email": EMAIL, "password": PASSWORD}
    assert result["result"].unique_id == EMAIL


async def test_user_flow_invalid_auth(hass, aioclient_mock):
    aioclient_mock.post(LOGIN_URL, status=401)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"email": EMAIL, "password": "wrong"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_cannot_connect(hass, aioclient_mock):
    aioclient_mock.post(LOGIN_URL, status=500)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"email": EMAIL, "password": PASSWORD}
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_already_configured(hass, config_entry, aioclient_mock):
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"email": EMAIL, "password": PASSWORD}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    # Aucune connexion tentée pour un compte déjà configuré
    assert aioclient_mock.call_count == 0


async def test_reauth_updates_password(hass, setup_integration, aioclient_mock):
    result = await setup_integration.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"password": "new"})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert setup_integration.data["password"] == "new"


async def test_import_from_yaml(hass, aioclient_mock, mock_setup_entry):
    aioclient_mock.post(LOGIN_URL, json={"token": "t", "id": USER_ID})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_IMPORT}, data={"email": EMAIL, "password": PASSWORD}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == EMAIL
