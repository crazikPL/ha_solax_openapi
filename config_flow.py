"""Config flow for the SolaX OpenAPI integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SolaxAuthError, SolaxApiError, SolaxOpenApiClient
from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_PLANT_ID, CONF_REGION, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CLIENT_ID): str,
        vol.Required(CONF_CLIENT_SECRET): str,
        vol.Required(CONF_REGION, default="eu"): vol.In(["eu", "us", "cn"]),
        vol.Optional(CONF_PLANT_ID): str,
    }
)


class SolaxOpenApiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SolaX OpenAPI."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
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
            else:
                unique_id = f"{user_input[CONF_CLIENT_ID]}_{user_input[CONF_REGION]}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"SolaX Cloud ({user_input[CONF_REGION]})", data=user_input)

        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors)
