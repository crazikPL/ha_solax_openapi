"""DataUpdateCoordinator for the SolaX OpenAPI integration."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SolaxApiError, SolaxOpenApiClient
from .const import (
    DEVICE_TYPE_BATTERY,
    DEVICE_TYPE_INVERTER,
    DOMAIN,
    FAST_UPDATE_INTERVAL,
    SLOW_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class SolaxOpenApiCoordinator(DataUpdateCoordinator):
    """Coordinates plant/device metadata + realtime polling."""

    def __init__(self, hass: HomeAssistant, client: SolaxOpenApiClient, plant_id: str | None = None) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=FAST_UPDATE_INTERVAL)
        self.client = client
        self.plant_id_filter = plant_id
        self._last_slow_refresh: datetime | None = None
        self.plants: dict[str, dict] = {}
        self.devices: dict[str, dict] = {}

    async def _async_update_data(self) -> dict:
        _LOGGER.debug("SolaX OpenAPI: Starting update cycle")
        try:
            await self._async_maybe_refresh_metadata()

            realtime_plants: dict[str, dict] = {}
            realtime_devices: dict[str, dict] = {}

            for plant_id in self.plants:
                _LOGGER.debug("SolaX OpenAPI: Polling plant realtime data for %s", plant_id)
                realtime_plants[plant_id] = await self.client.async_get_plant_realtime(plant_id)

            for device_sn, device in self.devices.items():
                device_type = device["deviceType"]
                if device_type not in (DEVICE_TYPE_INVERTER, DEVICE_TYPE_BATTERY):
                    continue
                _LOGGER.debug("SolaX OpenAPI: Polling device realtime data for %s", device_sn)
                data = await self.client.async_get_device_realtime(
                    device_sn, device_type, real_sn=device.get("_real_sn")
                )
                if data is not None:
                    realtime_devices[device_sn] = data

        except SolaxApiError as err:
            _LOGGER.warning("SolaX OpenAPI: Update cycle failed: %s", err)
            raise UpdateFailed(str(err)) from err

        _LOGGER.debug(
            "SolaX OpenAPI: Update cycle done (%d plants, %d devices with data)",
            len(realtime_plants), len(realtime_devices),
        )
        return {
            "plants": self.plants,
            "devices": self.devices,
            "plant_realtime": realtime_plants,
            "device_realtime": realtime_devices,
        }

    async def _async_maybe_refresh_metadata(self) -> None:
        """Refresh plant/device metadata on first run and then every 30 min."""
        now = datetime.now(timezone.utc)
        if self._last_slow_refresh is not None and (now - self._last_slow_refresh) < SLOW_UPDATE_INTERVAL:
            return

        plant_list = await self.client.async_get_plant_list(self.plant_id_filter)
        plants: dict[str, dict] = {}
        for plant in plant_list:
            plant_id = plant.get("plantId")
            if plant_id:
                plants[plant_id] = plant
        self.plants = plants

        devices: dict[str, dict] = {}
        for plant_id in plants:
            for device_type in (DEVICE_TYPE_INVERTER, DEVICE_TYPE_BATTERY):
                for device in await self.client.async_get_device_list(plant_id, device_type):
                    device_sn = device.get("deviceSn")
                    if not device_sn:
                        continue
                    device["deviceType"] = device_type
                    device["plantId"] = plant_id
                    devices[device_sn] = device

            # Fallback: if plant reports a battery capacity but no battery device
            # was found (seen in the wild for some SolaX accounts), synthesize one
            # so battery SOC/capacity sensors still get created.
            has_battery = any(d.get("plantId") == plant_id and d.get("deviceType") == DEVICE_TYPE_BATTERY for d in devices.values())
            battery_capacity = plants[plant_id].get("batteryCapacity", 0) or 0
            if not has_battery and battery_capacity > 0:
                inverter_sn = next(
                    (d.get("deviceSn") for d in devices.values() if d.get("plantId") == plant_id and d.get("deviceType") == DEVICE_TYPE_INVERTER),
                    None,
                )
                if inverter_sn:
                    fake_sn = f"{inverter_sn}_battery"
                    devices[fake_sn] = {
                        "deviceSn": fake_sn,
                        "plantId": plant_id,
                        "deviceType": DEVICE_TYPE_BATTERY,
                        "deviceModel": 0,
                        "ratedCapacity": battery_capacity,
                        "onlineStatus": 1,
                        "_synthetic": True,
                        "_real_sn": inverter_sn,
                    }

        self.devices = devices
        self._last_slow_refresh = now
