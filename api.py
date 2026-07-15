"""Thin async client for the SolaX OpenAPI (read-only subset).

Endpoints and auth flow reverse-derived from the open-source Predbat
project (springfall2008/batpred, apps/predbat/solax.py), which is the
only known open-source implementation of this newer OAuth-style SolaX
OpenAPI (as opposed to the older tokenId-based API).

Only GET/realtime endpoints are used here - no control/command endpoints
are implemented, since this integration is monitoring-only by design.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

from .const import BUSINESS_TYPE_RESIDENTIAL, REGIONS, SOLAX_API_CODES

_LOGGER = logging.getLogger(__name__)

TIMEOUT = 20


class SolaxApiError(Exception):
    """Raised when the SolaX API returns an error we can't recover from."""


class SolaxAuthError(SolaxApiError):
    """Raised when client_id/client_secret are rejected."""


class SolaxOpenApiClient:
    """Minimal async client for the SolaX OpenAPI."""

    def __init__(self, session: aiohttp.ClientSession, client_id: str, client_secret: str, region: str = "eu") -> None:
        self._session = session
        self._client_id = client_id
        self._client_secret = client_secret
        self._base_url = f"https://{REGIONS.get(region, REGIONS['eu'])}"
        self._access_token: str | None = None
        self._token_expiry: datetime | None = None

    async def async_validate(self) -> None:
        """Try to get a token - raises SolaxAuthError on bad credentials."""
        token = await self._async_get_token()
        if not token:
            raise SolaxAuthError("Could not authenticate with SolaX Cloud")

    async def _async_get_token(self) -> str | None:
        url = f"{self._base_url}/openapi/auth/get_token"
        payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "CICS",
        }
        timeout = aiohttp.ClientTimeout(total=TIMEOUT)
        async with self._session.post(url, json=payload, timeout=timeout) as resp:
            if resp.status != 200:
                raise SolaxApiError(f"Auth HTTP {resp.status}")
            data = await resp.json()

        code = data.get("code")
        if code == 10402:
            raise SolaxAuthError("Invalid client ID or secret")
        if code not in (0, 10000, None):
            raise SolaxApiError(SOLAX_API_CODES.get(code, f"Auth error {code}"))

        result = data.get("result", {})
        token = result.get("access_token")
        expires_in = result.get("expires_in", 2591999)
        if not token:
            raise SolaxApiError("No access_token in auth response")

        self._access_token = token
        self._token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        return token

    async def _async_request(self, path: str, params: dict | None = None, post: bool = False, json_data: dict | None = None) -> dict:
        if self._access_token is None or self._token_expiry is None or self._token_expiry < datetime.now(timezone.utc):
            await self._async_get_token()

        url = f"{self._base_url}{path}"
        headers = {
            "Authorization": f"bearer {self._access_token}",
            "Content-Type": "application/json",
        }
        timeout = aiohttp.ClientTimeout(total=TIMEOUT)

        if post:
            cm = self._session.post(url, headers=headers, json=json_data, timeout=timeout)
        else:
            cm = self._session.get(url, headers=headers, params=params, timeout=timeout)

        async with cm as resp:
            if resp.status != 200:
                raise SolaxApiError(f"HTTP {resp.status} for {path}")
            data = await resp.json()

        code = data.get("code")
        if code in (10400, 10401, 10402):
            # Token rejected - force refresh next call
            self._access_token = None
            self._token_expiry = None
            raise SolaxApiError(SOLAX_API_CODES.get(code, f"Auth error {code}"))
        if code not in (0, 10000, None):
            raise SolaxApiError(SOLAX_API_CODES.get(code, f"API error {code}"))

        return data

    async def _async_fetch_single(self, path: str, params: dict | None = None, post: bool = False, json_data: dict | None = None) -> Any:
        data = await self._async_request(path, params=params, post=post, json_data=json_data)
        return data.get("result", {})

    async def _async_fetch_paginated(self, path: str, base_params: dict, page_size: int = 100) -> list:
        all_records: list = []
        page = 1
        while True:
            params = dict(base_params)
            params["size"] = page_size
            params["pageNo"] = page
            data = await self._async_request(path, params=params)
            result = data.get("result", {}) or {}
            records = result.get("records", [])
            pages = result.get("pages", 1)
            all_records.extend(records)
            if page >= pages:
                break
            page += 1
        return all_records

    # ---- Public read-only calls -------------------------------------------------

    async def async_get_plant_list(self, plant_id: str | None = None) -> list[dict]:
        """Return list of plant info dicts."""
        params: dict[str, Any] = {"businessType": BUSINESS_TYPE_RESIDENTIAL}
        if plant_id:
            params["plantId"] = plant_id
        return await self._async_fetch_paginated("/openapi/v2/plant/page_plant_info", params)

    async def async_get_device_list(self, plant_id: str, device_type: int) -> list[dict]:
        """Return list of device info dicts for a plant + device type."""
        params = {
            "businessType": BUSINESS_TYPE_RESIDENTIAL,
            "plantId": plant_id,
            "deviceType": device_type,
        }
        return await self._async_fetch_paginated("/openapi/v2/device/page_device_info", params)

    async def async_get_plant_realtime(self, plant_id: str) -> dict:
        """Return plant-level realtime totals (yield, imported, exported, ...)."""
        params = {"plantId": plant_id, "businessType": BUSINESS_TYPE_RESIDENTIAL}
        return await self._async_fetch_single("/openapi/v2/plant/realtime_data", params=params) or {}

    async def async_get_device_realtime(self, device_sn: str, device_type: int, real_sn: str | None = None) -> dict | None:
        """Return realtime data for a single device (inverter or battery).

        Some SolaX accounts don't return a proper "Battery" device in the
        device list even though a battery is physically present (seen with
        low-voltage models such as X3-NEO-LV + EcoBSS). In that case pass
        real_sn = the inverter's serial number and requestSnType=1 is added,
        which asks the API to return the battery(ies) attached to that
        inverter instead of looking up device_sn directly. This mirrors the
        workaround already used by Predbat's SolaX Cloud component.
        """
        query_sn = real_sn or device_sn
        params = {
            "snList": [query_sn],
            "deviceType": device_type,
            "businessType": BUSINESS_TYPE_RESIDENTIAL,
        }
        if real_sn and real_sn != device_sn:
            params["requestSnType"] = 1  # 1 = Device SN, 2 = Register No
        result = await self._async_fetch_single("/openapi/v2/device/realtime_data", params=params)
        if result:
            return result[0]
        return None
