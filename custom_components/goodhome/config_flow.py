"""Config flow pour GoodHome integration."""
import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD

from .goodhome_api import GoodHomeAPI, GoodHomeConnectionError

_LOGGER = logging.getLogger(__name__)

DOMAIN = "goodhome"


async def _async_validate_login(hass, email, password):
    """Tester les credentials, retourne une clé d'erreur ou None."""
    api = GoodHomeAPI(None, None, email, password)
    try:
        if await hass.async_add_executor_job(api.login):
            return None
        return "invalid_auth"
    except GoodHomeConnectionError as e:
        _LOGGER.error("Cannot connect to GoodHome: %s", e)
        return "cannot_connect"
    except Exception as e:
        _LOGGER.exception("Unexpected error during login: %s", e)
        return "unknown"


class GoodHomeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for GoodHome."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]

            error = await _async_validate_login(self.hass, email, password)
            if error is None:
                # Créer l'entrée de configuration
                await self.async_set_unique_id(email)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"GoodHome ({email})",
                    data={
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                    },
                )
            errors["base"] = error

        # Afficher le formulaire
        data_schema = vol.Schema({
            vol.Required(CONF_EMAIL): str,
            vol.Required(CONF_PASSWORD): str,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]):
        """Start reauth when the stored credentials are rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Ask for a new password."""
        errors = {}
        reauth_entry = self._get_reauth_entry()
        email = reauth_entry.data[CONF_EMAIL]

        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            error = await _async_validate_login(self.hass, email, password)
            if error is None:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={CONF_PASSWORD: password},
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"email": email},
            errors=errors,
        )
