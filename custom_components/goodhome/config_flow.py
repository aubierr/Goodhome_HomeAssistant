"""Configuration de l'intégration GoodHome depuis l'interface."""
import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_ADDRESS, CONF_BLE_NAME, CONF_CONNECTION, CONF_SERIAL, CONNECTION_LOCAL, DOMAIN
from .goodhome_api import GoodHomeAuthError, GoodHomeClient, GoodHomeError

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema({vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str})


class GoodHomeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ajout d'un compte GoodHome (cloud) ou d'un radiateur en Bluetooth local."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialiser le parcours."""
        self._address: str | None = None
        self._ble_name: str | None = None

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
        """Choisir le mode : compte cloud, ou Bluetooth local (adaptateur nécessaire)."""
        return self.async_show_menu(step_id="user", menu_options=["cloud", "local"])

    async def async_step_cloud(self, user_input=None) -> ConfigFlowResult:
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
            step_id="cloud",
            # Pré-remplir l'email après une erreur, jamais le mot de passe
            data_schema=self.add_suggested_values_to_schema(
                USER_SCHEMA, {CONF_EMAIL: user_input[CONF_EMAIL]} if user_input else None
            ),
            errors=errors,
        )

    def _configured_ble_names(self) -> set[str]:
        """Noms et adresses des radiateurs déjà ajoutés."""
        configured = set()
        for entry in self._async_current_entries(include_ignore=False):
            configured.update(value for value in (entry.data.get(CONF_BLE_NAME), entry.data.get(CONF_ADDRESS)) if value)
        return configured

    async def async_step_local(self, user_input=None) -> ConfigFlowResult:
        """Choisir un radiateur parmi ceux visibles en Bluetooth."""
        from .ble_client import async_discovered_radiators, async_list_radiators

        configured = self._configured_ble_names()
        radiators = {
            address: name
            for address, name in (await async_list_radiators(self.hass)).items()
            if name not in configured and address not in configured
        }
        if user_input is not None:
            self._address = user_input[CONF_ADDRESS]
            self._ble_name = radiators.get(self._address, self._address)
            await self.async_set_unique_id(self._ble_name)
            self._abort_if_unique_id_configured()
            return await self.async_step_pair()

        if not radiators:
            return self.async_abort(reason="no_devices_found")
        # Radiateur déjà appairé (annoncé sans nom, nom retrouvé dans BlueZ) : afficher aussi son adresse
        announced = async_discovered_radiators(self.hass)
        labels = {
            address: f"{name} ({address})" if announced.get(address) == address != name else name
            for address, name in radiators.items()
        }
        return self.async_show_form(
            step_id="local", data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(labels)})
        )

    async def async_step_bluetooth(self, discovery_info) -> ConfigFlowResult:
        """Radiateur détecté par le Bluetooth de Home Assistant."""
        # Le nom est stable, l'adresse change tant que le radiateur n'est pas appairé
        self._address = discovery_info.address
        self._ble_name = discovery_info.name
        await self.async_set_unique_id(self._ble_name)
        self._abort_if_unique_id_configured()
        if self._ble_name in self._configured_ble_names():
            return self.async_abort(reason="already_configured")
        self.context["title_placeholders"] = {"name": self._ble_name}
        return await self.async_step_pair()

    async def async_step_pair(self, user_input=None) -> ConfigFlowResult:
        """Appairer le radiateur après l'appui sur son bouton d'appairage."""
        from .ble_client import (
            GoodHomeBleError,
            GoodHomeBleNotFound,
            GoodHomeBlePairingRejected,
            async_discovered_radiators,
            async_pair_radiator,
        )

        errors = {}
        placeholders = {"name": self._ble_name, "error": ""}
        if user_input is not None:
            # L'adresse a pu changer depuis la détection : reprendre la plus récente pour ce nom
            current = {name: address for address, name in async_discovered_radiators(self.hass).items()}
            address = current.get(self._ble_name, self._address)
            try:
                fixed_address, serial, state = await async_pair_radiator(self.hass, address, self._ble_name)
            except GoodHomeBleNotFound as err:
                _LOGGER.warning("Pairing with %s failed: %s", self._ble_name, err)
                errors["base"] = "not_found"
            except GoodHomeBlePairingRejected as err:
                _LOGGER.warning("Pairing with %s failed: %s", self._ble_name, err)
                errors["base"] = "pair_rejected"
            except GoodHomeBleError as err:
                _LOGGER.warning("Pairing with %s failed: %s", self._ble_name, err)
                errors["base"] = "pair_failed"
                placeholders["error"] = str(err)
            else:
                await self.async_set_unique_id(serial, raise_on_progress=False)
                self._abort_if_unique_id_configured(updates={CONF_ADDRESS: fixed_address})
                return self.async_create_entry(
                    title=f"GoodHome {state.get('roomName') or self._ble_name}",
                    data={
                        CONF_CONNECTION: CONNECTION_LOCAL,
                        CONF_ADDRESS: fixed_address,
                        CONF_SERIAL: serial,
                        CONF_BLE_NAME: self._ble_name,
                    },
                )

        return self.async_show_form(step_id="pair", description_placeholders=placeholders, errors=errors)

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
