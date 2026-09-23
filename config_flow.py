"""Config flow for the SolaX OpenAPI integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SolaxAuthError, SolaxApiError, SolaxOpenApiClient
from .const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_NAME_PREFIX,
    CONF_PLANT_ID,
    CONF_REGION,
    DEFAULT_NAME_PREFIX,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _build_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Build the user-step schema.

    When `defaults` is given (e.g. on reconfigure, from the existing config
    entry), every field - including client_id/client_secret - is pre-filled
    with the current value so the user can simply overwrite it (for example
    after rotating their SolaX Cloud API key) instead of the field being
    stuck showing nothing.
    """
    defaults = defaults or {}

    def _required(key: str):
        return vol.Required(key, default=defaults[key]) if key in defaults else vol.Required(key)

    def _optional(key: str, fallback: Any = None):
        if key in defaults:
            return vol.Optional(key, default=defaults[key])
        if fallback is not None:
            return vol.Optional(key, default=fallback)
        return vol.Optional(key)

    return vol.Schema(
        {
            _required(CONF_CLIENT_ID): str,
            _required(CONF_CLIENT_SECRET): str,
            vol.Required(CONF_REGION, default=defaults.get(CONF_REGION, "eu")): vol.In(["eu", "us", "cn"]),
            _optional(CONF_PLANT_ID): str,
            _optional(CONF_NAME_PREFIX, fallback=DEFAULT_NAME_PREFIX): str,
        }
    )


class SolaxOpenApiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SolaX OpenAPI."""

    VERSION = 1

    async def _async_validate_credentials(self, user_input: dict[str, Any], errors: dict[str, str]) -> None:
        """Try to authenticate against SolaX Cloud with the given credentials."""
        session = async_get_clientsession(self.hass)
        client = SolaxOpenApiClient(
            session,
            user_input[CONF_CLIENT_ID],
            user_input[CONF_CLIENT_SECRET],
            user_input[CONF_REGION],
        )
        try:
            await client.async_validate()
        except SolaxAuthError:
            errors["base"] = "invalid_auth"
        except SolaxApiError:
            errors["base"] = "cannot_connect"
        except Exception:  # pragma: no cover - safety net
            _LOGGER.exception("Unexpected error validating SolaX OpenAPI credentials")
            errors["base"] = "unknown"

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Handle the initial setup step, and reconfiguration (re-auth / edit settings)."""
        errors: dict[str, str] = {}
        is_reconfigure = self.source == config_entries.SOURCE_RECONFIGURE
        reconfigure_entry = self._get_reconfigure_entry() if is_reconfigure else None

        if user_input is not None:
            await self._async_validate_credentials(user_input, errors)

            if not errors:
                unique_id = f"{user_input[CONF_CLIENT_ID]}_{user_input[CONF_REGION]}"
                await self.async_set_unique_id(unique_id)
                title = f"SolaX Cloud ({user_input[CONF_REGION]})"

                if reconfigure_entry is not None:
                    # Full credential re-entry (client_id/secret can change
                    # entirely after an API key rotation) - don't abort on
                    # a "different account" unique_id, just update this entry.
                    return self.async_update_reload_and_abort(
                        reconfigure_entry,
                        title=title,
                        data=user_input,
                    )

                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=title, data=user_input)

        # Pre-fill the form: with what the user just submitted (if it failed
        # validation), otherwise with the existing entry's data when we're
        # reconfiguring, otherwise empty for a brand new setup.
        if user_input is not None:
            defaults = user_input
        elif reconfigure_entry is not None:
            defaults = dict(reconfigure_entry.data)
        else:
            defaults = {}

        return self.async_show_form(
            step_id="user",
            data_schema=_build_schema(defaults),
            errors=errors,
            description_placeholders={"name_prefix_example": DEFAULT_NAME_PREFIX},
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Entry point when the user picks "Reconfigure" on an existing entry."""
        return await self.async_step_user(user_input)
