from __future__ import annotations

import asyncio
import logging
import re
from threading import Lock
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)
PHOTON_SEARCH_URL = "https://photon.komoot.io/api/"
LOCATION_ERROR_MESSAGE = "We couldn't identify that location. Try a city and state such as New York, NY."


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
            raise LocationResolutionError(LOCATION_ERROR_MESSAGE)

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

        resolved = await self._resolve_with_nominatim(normalized, country)
        if resolved is None:
            resolved = await self._resolve_with_photon(normalized, country)
        if resolved is None:
            raise LocationResolutionError(LOCATION_ERROR_MESSAGE)

        with self._cache_lock:
            self._cache[cache_key] = resolved
        return {
            **resolved,
            "boundingbox": list(resolved["boundingbox"])
            if resolved.get("boundingbox") is not None
            else None,
        }

    async def _resolve_with_nominatim(self, location: str, country: str) -> dict[str, Any] | None:
        params = {
            "q": location,
            "countrycodes": "us",
            "format": "jsonv2",
            "limit": 1,
            "addressdetails": 1,
        }
        try:
            async with asyncio.timeout(self.timeout):
                async with httpx.AsyncClient(timeout=self.timeout, headers={"User-Agent": self.user_agent}) as client:
                    response = await client.get(self.api_url, params=params)
        except (httpx.HTTPError, TimeoutError) as exc:
            logger.warning("Nominatim location lookup failed: %s", exc)
            return None

        if response.status_code >= 400:
            logger.warning("Nominatim location lookup returned HTTP %s", response.status_code)
            return None

        try:
            payload = response.json()
        except ValueError as exc:
            logger.warning("Nominatim location lookup returned invalid JSON: %s", exc)
            return None
        if not isinstance(payload, list) or not payload:
            logger.info("Nominatim did not resolve location %s", location)
            return None

        result = payload[0]
        if not isinstance(result, dict):
            return None
        address = result.get("address") or {}
        country_code = (address.get("country_code") or "").lower()
        if country_code and country_code != "us":
            raise LocationResolutionError("BuyerBridge currently focuses on United States locations only.")

        try:
            lat = float(result["lat"])
            lon = float(result["lon"])
        except (KeyError, TypeError, ValueError):
            logger.warning("Nominatim location lookup returned invalid coordinates for %s", location)
            return None
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            logger.warning("Nominatim location lookup returned out-of-range coordinates for %s", location)
            return None

        bounding = result.get("boundingbox")
        return {
            "latitude": lat,
            "longitude": lon,
            "display_name": result.get("display_name") or location,
            "city": address.get("city") or address.get("town") or address.get("village") or location,
            "state": address.get("state") or address.get("state_district"),
            "country": address.get("country") or country,
            "boundingbox": bounding,
        }

    async def _resolve_with_photon(self, location: str, country: str) -> dict[str, Any] | None:
        params = {
            "q": location,
            "countrycode": "US",
            "limit": 1,
        }
        try:
            async with asyncio.timeout(self.timeout):
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    headers={"User-Agent": "BuyerBridge/1.0 (buyer discovery application)"},
                ) as client:
                    response = await client.get(PHOTON_SEARCH_URL, params=params)
        except (httpx.HTTPError, TimeoutError) as exc:
            logger.warning("Photon location lookup failed: %s", exc)
            return None

        if response.status_code >= 400:
            logger.warning("Photon location lookup returned HTTP %s", response.status_code)
            return None

        try:
            payload = response.json()
        except ValueError as exc:
            logger.warning("Photon location lookup returned invalid JSON: %s", exc)
            return None
        features = payload.get("features") if isinstance(payload, dict) else None
        if not isinstance(features, list) or not features or not isinstance(features[0], dict):
            logger.info("Photon did not resolve location %s", location)
            return None

        feature = features[0]
        properties = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
        if not isinstance(properties, dict) or not isinstance(coordinates, (list, tuple)) or len(coordinates) < 2:
            logger.warning("Photon location lookup returned incomplete data for %s", location)
            return None

        country_code = str(properties.get("countrycode") or "").lower()
        if country_code and country_code != "us":
            raise LocationResolutionError("BuyerBridge currently focuses on United States locations only.")
        try:
            lon, lat = float(coordinates[0]), float(coordinates[1])
        except (TypeError, ValueError):
            logger.warning("Photon location lookup returned invalid coordinates for %s", location)
            return None
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            logger.warning("Photon location lookup returned out-of-range coordinates for %s", location)
            return None

        extent = properties.get("extent")
        boundingbox = None
        if isinstance(extent, (list, tuple)) and len(extent) == 4:
            try:
                west, south, east, north = (float(value) for value in extent)
                if south <= north and west <= east:
                    boundingbox = [south, north, west, east]
            except (TypeError, ValueError):
                logger.warning("Photon location lookup returned invalid bounds for %s", location)

        display_name = properties.get("name") or location
        address_parts = [
            properties.get("city") or properties.get("town") or properties.get("village") or display_name,
            properties.get("state"),
            properties.get("country") or country,
        ]
        return {
            "latitude": lat,
            "longitude": lon,
            "display_name": ", ".join(str(part) for part in address_parts if part),
            "city": properties.get("city") or properties.get("town") or properties.get("village") or display_name,
            "state": properties.get("state"),
            "country": properties.get("country") or country,
            "boundingbox": boundingbox,
        }
