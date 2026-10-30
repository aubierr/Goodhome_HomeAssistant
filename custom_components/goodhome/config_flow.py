"""Configuration de l'intégration GoodHome depuis l'interface."""
import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN
from .goodhome_api import GoodHomeAuthError, GoodHomeClient, GoodHomeError

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema({vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str})


class GoodHomeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ajout d'un compte GoodHome."""

    VERSION = 1

    async def _async_validate_login(self, email, password):
        """Tester les identifiants ; renvoie une clé d'erreur ou None."""
        client = GoodHomeClient(async_get_clientsession(self.hass), email, password)
        try:
            await client.async_login()
        except GoodHomeAuthError:
            return "invalid_auth"
        except GoodHomeError as err:
            _LOGGER.error("Cannot connect to GoodHome: %s", err)
            return "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error during GoodHome login")
            return "unknown"
        return None

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        """Demander email et mot de passe."""
        errors = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL]
            await self.async_set_unique_id(email)
            self._abort_if_unique_id_configured()
            error = await self._async_validate_login(email, user_input[CONF_PASSWORD])
            if error is None:
                return self.async_create_entry(title=f"GoodHome ({email})", data=user_input)
            errors["base"] = error

        return self.async_show_form(
            step_id="user",
            # Pré-remplir l'email après une erreur, jamais le mot de passe
            data_schema=self.add_suggested_values_to_schema(
                USER_SCHEMA, {CONF_EMAIL: user_input[CONF_EMAIL]} if user_input else None
            ),
            errors=errors,
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Importer une ancienne configuration YAML."""
        email = import_data[CONF_EMAIL]
        await self.async_set_unique_id(email)
        self._abort_if_unique_id_configured()
        error = await self._async_validate_login(email, import_data[CONF_PASSWORD])
        if error is not None:
            return self.async_abort(reason=error)
        return self.async_create_entry(
            title=f"GoodHome ({email})",
            data={CONF_EMAIL: email, CONF_PASSWORD: import_data[CONF_PASSWORD]},
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Les identifiants enregistrés sont refusés."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None) -> ConfigFlowResult:
        """Demander le nouveau mot de passe."""
        errors = {}
        reauth_entry = self._get_reauth_entry()
        email = reauth_entry.data[CONF_EMAIL]
        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            error = await self._async_validate_login(email, password)
            if error is None:
                return self.async_update_reload_and_abort(reauth_entry, data_updates={CONF_PASSWORD: password})
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"email": email},
            errors=errors,
        )
