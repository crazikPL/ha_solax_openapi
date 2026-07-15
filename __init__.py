"""The SolaX OpenAPI (Cloud) integration - read-only monitoring."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SolaxOpenApiClient
from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_PLANT_ID, CONF_REGION, DOMAIN
from .coordinator import SolaxOpenApiCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SolaX OpenAPI from a config entry."""
    session = async_get_clientsession(hass)
    client = SolaxOpenApiClient(
        session,
        entry.data[CONF_CLIENT_ID],
        entry.data[CONF_CLIENT_SECRET],
        entry.data[CONF_REGION],
    )
    coordinator = SolaxOpenApiCoordinator(hass, client, entry.data.get(CONF_PLANT_ID))

    # First refresh must succeed (and must discover plants/devices) before we
    # forward to the sensor platform, since entities are created once from
    # whatever coordinator.data["plants"]/["devices"] contain at that point.
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
