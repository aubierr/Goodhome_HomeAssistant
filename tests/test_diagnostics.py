"""Tests des diagnostics."""
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
