"""Diagnostics GoodHome : données à joindre à un rapport de bug."""
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD

# userHash identifie la maison ; roomName peut révéler l'agencement du logement
TO_REDACT = {CONF_EMAIL, CONF_PASSWORD, "userHash", "name", "roomName"}


async def async_get_config_entry_diagnostics(hass, entry):
    """Diagnostics du compte, sans identifiants ni noms."""
    coordinator = entry.runtime_data.coordinator
    push = entry.runtime_data.push
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "last_update_success": coordinator.last_update_success,
        # Écoute temps réel : sans elle, les changements n'arrivent qu'à la relecture de l'API
        "push": {
            "connected": push.connected,
            "connections": push.connections,
            "last_event": push.last_event.isoformat() if push.last_event else None,
            "last_error": push.last_error,
        },
        # Identifiants et noms masqués : seuls les réglages et mesures restent
        "devices": [
            async_redact_data(device, TO_REDACT | {"id"})
            for device in (coordinator.data or {}).values()
        ],
    }
