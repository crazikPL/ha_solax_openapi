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
        # Devices that have failed with a non-recoverable error (e.g. permission
        # denied). We keep polling them (in case SolaX Cloud fixes the
        # authorization on their end) but we no longer let a failure here take
        # down the whole coordinator update.
        self._device_errors: dict[str, str] = {}

    async def _async_update_data(self) -> dict:
        _LOGGER.debug("SolaX OpenAPI: Starting update cycle")

        try:
            await self._async_maybe_refresh_metadata()
        except SolaxApiError as err:
            _LOGGER.warning("SolaX OpenAPI: Update cycle failed: %s", err)
            raise UpdateFailed(str(err)) from err

        realtime_plants: dict[str, dict] = {}
        realtime_devices: dict[str, dict] = {}
        cycle_had_success = False

        # --- Plant-level realtime -------------------------------------------------
        for plant_id in self.plants:
            _LOGGER.debug("SolaX OpenAPI: Polling plant realtime data for %s", plant_id)
            try:
                realtime_plants[plant_id] = await self.client.async_get_plant_realtime(plant_id)
                cycle_had_success = True
            except SolaxApiError as err:
                _LOGGER.warning(
                    "SolaX OpenAPI: Plant realtime poll failed for %s: %s", plant_id, err
                )

        # --- Device-level realtime --------------------------------------------------
        for device_sn, device in self.devices.items():
            device_type = device["deviceType"]
            if device_type not in (DEVICE_TYPE_INVERTER, DEVICE_TYPE_BATTERY):
                continue

            _LOGGER.debug("SolaX OpenAPI: Polling device realtime data for %s", device_sn)
            try:
                data = await self.client.async_get_device_realtime(
                    device_sn, device_type, real_sn=device.get("_real_sn")
                )
            except SolaxApiError as err:
                # A single device failing (e.g. "User has no device data
                # permission" for a synthesized/unauthorized device) must not
                # take down realtime data for every other device.
                if self._device_errors.get(device_sn) != str(err):
                    # Only log at WARNING the first time we see this specific
                    # error for this device, to avoid spamming the log every
                    # 30 seconds forever. Repeats go to DEBUG.
                    _LOGGER.warning(
                        "SolaX OpenAPI: Device realtime poll failed for %s (%s), "
                        "will keep retrying but this device's sensors will be "
                        "unavailable until it succeeds: %s",
                        device_sn,
                        "synthetic battery" if device.get("_synthetic") else "device",
                        err,
                    )
                else:
                    _LOGGER.debug(
                        "SolaX OpenAPI: Device realtime poll still failing for %s: %s",
                        device_sn, err,
                    )
                self._device_errors[device_sn] = str(err)
                continue

            # Success - clear any previously recorded error for this device.
            self._device_errors.pop(device_sn, None)
            cycle_had_success = True
            if data is not None:
                realtime_devices[device_sn] = data

        # Only raise UpdateFailed if literally nothing succeeded this cycle -
        # e.g. the whole cloud API is down or the token is bad. A single bad
        # device (permission error, offline device, etc.) should just mean
        # that device's sensors go unavailable, not the whole integration.
        if not cycle_had_success and (self.plants or self.devices):
            raise UpdateFailed(
                "All plant/device realtime polls failed this cycle - see warnings above"
            )

        _LOGGER.debug(
            "SolaX OpenAPI: Update cycle done (%d plants, %d devices with data, %d devices erroring)",
            len(realtime_plants), len(realtime_devices), len(self._device_errors),
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
            has_battery = any(
                d.get("plantId") == plant_id and d.get("deviceType") == DEVICE_TYPE_BATTERY
                for d in devices.values()
            )
            battery_capacity = plants[plant_id].get("batteryCapacity", 0) or 0
            if not has_battery and battery_capacity > 0:
                inverter_sn = next(
                    (
                        d.get("deviceSn")
                        for d in devices.values()
                        if d.get("plantId") == plant_id and d.get("deviceType") == DEVICE_TYPE_INVERTER
                    ),
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
