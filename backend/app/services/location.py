from __future__ import annotations

import asyncio
import re
from threading import Lock
from typing import Any

import httpx

from app.config import settings


class LocationResolutionError(ValueError):
    pass


class LocationResolver:
    async def resolve(self, location: str, country: str) -> dict[str, Any]:
        raise NotImplementedError("Location resolver must be implemented.")


class NominatimLocationResolver(LocationResolver):
    _cache: dict[str, dict[str, Any]] = {}
    _cache_lock = Lock()

    def __init__(self, api_url: str | None = None, user_agent: str | None = None, timeout: float = 12.0):
        self.api_url = api_url or settings.GEOCODING_API_URL
        self.user_agent = user_agent or settings.GEOCODING_USER_AGENT
        self.timeout = timeout

    async def resolve(self, location: str, country: str) -> dict[str, Any]:
        normalized = (location or "").strip()
        if not normalized:
            raise LocationResolutionError("We couldn't identify that location. Try a city and state such as New York, NY.")

        cache_key = f"{self.api_url.rstrip('/')}|{normalized.casefold()}|{(country or 'United States').casefold()}"
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return {
                    **cached,
                    "boundingbox": list(cached["boundingbox"])
                    if cached.get("boundingbox") is not None
                    else None,
                }

        params = {
            "q": normalized,
            "countrycodes": "us",
            "format": "jsonv2",
            "limit": 1,
            "addressdetails": 1,
        }
        try:
            async with asyncio.timeout(self.timeout):
                async with httpx.AsyncClient(timeout=self.timeout, headers={"User-Agent": self.user_agent}) as client:
                    response = await client.get(self.api_url, params=params)
        except (httpx.HTTPError, TimeoutError):
            raise LocationResolutionError("We couldn't identify that location. Try a city and state such as New York, NY.")

        if response.status_code >= 400:
            raise LocationResolutionError("We couldn't identify that location. Try a city and state such as New York, NY.")

        payload = response.json()
        if not isinstance(payload, list) or not payload:
            raise LocationResolutionError("We couldn't identify that location. Try a city and state such as New York, NY.")

        result = payload[0]
        address = result.get("address") or {}
        country_code = (address.get("country_code") or "").lower()
        if country_code and country_code != "us":
            raise LocationResolutionError("BuyerBridge currently focuses on United States locations only.")

        lat = float(result.get("lat", 0))
        lon = float(result.get("lon", 0))
        bounding = result.get("boundingbox")
        resolved = {
            "latitude": lat,
            "longitude": lon,
            "display_name": result.get("display_name") or normalized,
            "city": address.get("city") or address.get("town") or address.get("village") or normalized,
            "state": address.get("state") or address.get("state_district"),
            "country": address.get("country") or country,
            "boundingbox": bounding,
        }

        with self._cache_lock:
            self._cache[cache_key] = resolved
        return resolved
