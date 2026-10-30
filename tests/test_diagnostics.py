"""Tests des diagnostics."""
from datetime import UTC, datetime

from custom_components.goodhome.diagnostics import async_get_config_entry_diagnostics

from .conftest import DEVICE_ID, EMAIL, PASSWORD

REDACTED = "**REDACTED**"


async def test_diagnostics_hide_credentials_and_names(hass, setup_integration):
    diagnostics = await async_get_config_entry_diagnostics(hass, setup_integration)

    assert diagnostics["entry"] == {"email": REDACTED, "password": REDACTED}
    device = diagnostics["devices"][0]
    assert device["id"] == REDACTED
    assert device["name"] == REDACTED
    assert device["state"]["roomName"] == REDACTED
    assert device["state"]["userHash"] == REDACTED
    # Les réglages et mesures restent visibles
    assert device["state"]["targetMode"] == 60

    text = str(diagnostics)
    for secret in (EMAIL, PASSWORD, DEVICE_ID, "CUISINE"):
        assert secret not in text


async def test_diagnostics_show_push_status(hass, setup_integration):
    push = setup_integration.runtime_data.push
    push.connected, push.connections, push.last_error = True, 2, "GoodHomePushSessionLost('HTTP 400')"
    push.last_event = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)

    diagnostics = await async_get_config_entry_diagnostics(hass, setup_integration)

    assert diagnostics["push"] == {
        "connected": True,
        "connections": 2,
        "last_event": "2026-10-30T12:00:00+00:00",
        "last_error": "GoodHomePushSessionLost('HTTP 400')",
    }
