from __future__ import annotations

import logging
import math
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

OVERPASS_ENDPOINTS = (
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)
PHOTON_REVERSE_URL = "https://photon.komoot.io/reverse"
PHOTON_USER_AGENT = "BuyerBridge/1.0 (buyer discovery application)"
PHOTON_TAGS_BY_BUYER_TYPE = {
    "interior designers": (
        "craft:interior_design",
        "office:interior_design",
        "shop:furniture",
        "shop:interior_decoration",
        "shop:decor",
    ),
    "interior design studios": (
        "craft:interior_design",
        "office:interior_design",
        "shop:furniture",
        "shop:interior_decoration",
    ),
    "furniture stores": ("shop:furniture", "shop:home_furniture"),
    "home decor stores": (
        "shop:decor",
        "shop:interior_decoration",
        "shop:gift",
        "shop:home_furniture",
        "shop:furniture",
    ),
    "home furnishing retailers": ("shop:home_furniture", "shop:furniture", "shop:decor"),
    "home staging companies": (
        "craft:interior_design",
        "office:interior_design",
        "shop:furniture",
        "shop:home_furniture",
    ),
    "gift/home stores": ("shop:gift", "shop:decor", "shop:home_furniture"),
    "gift & home stores": ("shop:gift", "shop:decor", "shop:home_furniture"),
    "other": ("shop:furniture", "shop:home_furniture", "shop:decor", "shop:gift"),
}


class BusinessSearchProvider:
    async def search(self, query: str, location: dict[str, Any] | str, limit: int):
        raise NotImplementedError("Business search provider must be implemented.")


class BusinessSearchService:
    def __init__(self, provider: BusinessSearchProvider | None = None):
        self.provider = provider

    async def search(self, query: str, location: dict[str, Any] | str, limit: int):
        if self.provider is None:
            raise ValueError("No business search provider configured.")
        return await self.provider.search(query=query, location=location, limit=limit)


BUYER_TYPE_TAG_MAP = {
    "interior designers": ["shop=furniture", "shop=home_furniture", "craft=interior_design", "shop=gift", "shop=decor"],
    "interior design studios": ["shop=furniture", "shop=home_furniture", "craft=interior_design", "shop=gift"],
    "home decor stores": ["shop=decor", "shop=gift", "shop=home_furniture", "shop=furniture"],
    "furniture stores": ["shop=furniture", "shop=home_furniture"],
    "home furnishing retailers": ["shop=home_furniture", "shop=furniture", "shop=decor"],
    "home staging companies": ["shop=home_furniture", "shop=interior_decoration", "shop=furniture"],
    "interior architecture firms": ["craft=interior_design", "shop=furniture", "shop=home_furniture"],
    "gift/home stores": ["shop=gift", "shop=decor", "shop=home_furniture"],
    "boutique home stores": ["shop=decor", "shop=gift", "shop=home_furniture", "shop=furniture"],
    "other": ["shop=home_furniture", "shop=furniture", "shop=decor", "shop=gift"],
}


def normalize_name(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def extract_osm_website(tags: dict[str, Any]) -> str | None:
    website_fields = ("website", "contact:website", "url", "contact:url")
    for field in website_fields:
        value = normalize_name(tags.get(field))
        if value:
            return value

    osm_tags = tags.get("osm_tags")
    if isinstance(osm_tags, dict):
        for field in website_fields:
            value = normalize_name(osm_tags.get(field))
            if value:
                return value
    elif isinstance(osm_tags, list):
        for item in osm_tags:
            if isinstance(item, dict) and item.get("key") in website_fields:
                value = normalize_name(item.get("value"))
                if value:
                    return value

    return None


def deduplicate_businesses(rows: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for item in rows:
        business_name = (item.get("business_name") or "").strip().lower()
        raw_website = (item.get("website") or "").strip().lower()
        parsed_website = urlparse(raw_website if "://" in raw_website else f"//{raw_website}")
        website_host = (parsed_website.hostname or "").removeprefix("www.")
        phone = re.sub(r"\D", "", item.get("phone") or "")
        address = re.sub(r"\s+", " ", (item.get("address") or "").strip().lower())

        signatures: list[tuple[str, str]] = []
        provider_id = item.get("provider_id")
        if provider_id:
            signatures.append(("provider", str(provider_id)))
        if website_host:
            signatures.append(("website", website_host))
        if len(phone) >= 7:
            signatures.append(("phone", phone))
        if business_name and address and address not in {"address unavailable", "unknown"}:
            signatures.append(("name-address", f"{business_name}|{address}"))

        if not signatures:
            continue
        if any(signature in seen for signature in signatures):
            continue
        seen.update(signatures)
        deduped.append(item)
    return deduped


def score_business(business: dict, buyer_type: str, product_keywords: list[str]) -> int:
    score = 0
    normalized_buyer = buyer_type.lower()
    business_category = (business.get("category") or "").lower()
    if any(term in normalized_buyer for term in ["designer", "design", "furniture", "decor", "gift", "home"]):
        score += 30
    if business_category and any(term in business_category for term in ["furniture", "decor", "home", "gift", "design"]):
        score += 15
    if product_keywords:
        haystack = " ".join(
            filter(
                None,
                [
                    business.get("business_name") or "",
                    business.get("category") or "",
                    business.get("address") or "",
                ],
            )
        ).lower()
        if any(keyword.lower() in haystack for keyword in product_keywords):
            score += 20
    if business.get("city") or business.get("state"):
        score += 20
    if business.get("website"):
        score += 10
    if business.get("email"):
        score += 20
    return min(score, 100)


def get_supported_tags(buyer_type: str) -> list[str]:
    return BUYER_TYPE_TAG_MAP.get(buyer_type.lower(), BUYER_TYPE_TAG_MAP["other"])[:3]


def split_bbox_into_tiles(bbox: list[float] | tuple[float, float, float, float], tile_size: float | None = None) -> list[tuple[float, float, float, float]]:
    if len(bbox) != 4:
        return []

    south, north, west, east = [float(value) for value in bbox]
    height = max(0.0, north - south)
    width = max(0.0, east - west)
    if tile_size is None:
        tile_size = 0.12

    if max(height, width) <= tile_size:
        return [(south, west, north, east)]

    column_count = max(2, int(math.ceil(width / tile_size)))
    row_count = max(2, int(math.ceil(height / tile_size)))
    tiles: list[tuple[float, float, float, float]] = []

    for row_index in range(row_count):
        row_south = south + (height * row_index / row_count)
        row_north = south + (height * (row_index + 1) / row_count)
        for col_index in range(column_count):
            col_west = west + (width * col_index / column_count)
            col_east = west + (width * (col_index + 1) / column_count)
            tiles.append((row_south, col_west, row_north, col_east))
    center_lat = (south + north) / 2.0
    center_lon = (west + east) / 2.0
    tiles.sort(
        key=lambda tile: (
            ((tile[0] + tile[2]) / 2.0 - center_lat) ** 2
            + ((tile[1] + tile[3]) / 2.0 - center_lon) ** 2
        )
    )
    return tiles


def build_overpass_query_for_bbox(buyer_type: str, bbox: tuple[float, float, float, float], limit: int) -> str:
    south, west, north, east = bbox
    tags = get_supported_tags(buyer_type)
    tag_clause = "\n".join([f"nwr[{tag}]({south},{west},{north},{east});" for tag in tags])
    max_results = max(8, min(limit, 25))
    query = f"""
    [out:json][timeout:25];
    (
      {tag_clause}
    );
    out center tags {max_results};
    """.strip()
    return query


def build_overpass_query(buyer_type: str, location: dict[str, Any], limit: int) -> str:
    lat = location.get("latitude")
    lon = location.get("longitude")
    bbox = location.get("boundingbox") or []
    if lat is None or lon is None:
        raise ValueError("Location coordinates are required for buyer discovery.")

    if len(bbox) == 4:
        south, north, west, east = [float(value) for value in bbox]
        return build_overpass_query_for_bbox(buyer_type, (south, west, north, east), limit)

    radius = 3000
    tags = get_supported_tags(buyer_type)
    tag_clause = "\n".join([f"nwr[{tag}](around:{radius},{lat},{lon});" for tag in tags])
    max_results = max(8, min(limit, 25))
    query = f"""
    [out:json][timeout:25];
    (
      {tag_clause}
    );
    out center tags {max_results};
    """.strip()
    return query


class OverpassBusinessSearchProvider(BusinessSearchProvider):
    def __init__(self, api_url: str | None = None, user_agent: str | None = None):
        self.api_urls = (api_url,) if api_url else OVERPASS_ENDPOINTS
        self.user_agent = user_agent or settings.OVERPASS_USER_AGENT

    async def search(self, query: str, location: dict[str, Any] | str, limit: int):
        if isinstance(location, str):
            raise ValueError("A resolved location is required before using the Overpass provider.")

        latitude = location.get("latitude")
        longitude = location.get("longitude")
        if latitude is None or longitude is None:
            raise ValueError("Location resolution did not produce usable coordinates.")

        location_without_boundingbox = {
            key: value for key, value in location.items() if key != "boundingbox"
        }
        overpass_query = build_overpass_query(query, location_without_boundingbox, limit)
        logger.info(
            "Overpass buyer search around %s,%s for %s",
            latitude,
            longitude,
            query,
        )
        unique_businesses: list[dict] = []
        seen_provider_ids: set[str] = set()
        request_succeeded = False

        for endpoint in self.api_urls:
            logger.info("Attempting Overpass request to %s", endpoint)
            try:
                async with httpx.AsyncClient(timeout=12.0, headers={"User-Agent": self.user_agent}) as client:
                    response = await client.post(endpoint, data=overpass_query)
            except (httpx.RequestError, TimeoutError) as exc:
                logger.warning(
                    "Overpass request to %s failed with %s: %s",
                    endpoint,
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )
                continue

            payload = None
            valid_json = False
            try:
                payload = response.json()
                valid_json = True
            except ValueError as exc:
                if response.status_code == 200:
                    logger.warning("Overpass returned non-JSON from %s: %s", endpoint, exc, exc_info=True)

            elements = payload.get("elements") if isinstance(payload, dict) else None
            element_count = len(elements) if isinstance(elements, list) else 0
            logger.info(
                "Overpass response from %s: valid_json=%s, elements=%s",
                endpoint,
                str(valid_json).lower(),
                element_count,
            )

            if response.status_code != 200:
                logger.warning(
                    "Overpass request to %s returned HTTP status %s",
                    endpoint,
                    response.status_code,
                )
                continue

            if not valid_json:
                continue

            if not isinstance(payload, dict) or not isinstance(payload.get("elements", []), list):
                logger.warning("Overpass returned an invalid payload from %s", endpoint)
                continue
            if isinstance(payload.get("remark"), str) and "timeout" in payload["remark"].lower():
                logger.warning("Overpass query timed out at %s: %s", endpoint, payload["remark"])
                continue

            request_succeeded = True
            for element in payload.get("elements", []):
                tags = element.get("tags") or {}
                name = normalize_name(tags.get("name") or tags.get("brand")) or "Business name unavailable"
                category = tags.get("shop") or tags.get("craft") or tags.get("amenity") or "Business"
                address = tags.get("addr:street")
                city = tags.get("addr:city") or location.get("city")
                state = tags.get("addr:state") or location.get("state")
                country = tags.get("addr:country") or "United States"
                website = extract_osm_website(tags)
                phone = tags.get("phone") or tags.get("contact:phone")
                email = tags.get("email") or tags.get("contact:email")

                provider_id = f"osm:{element.get('type')}:{element.get('id')}"
                if provider_id in seen_provider_ids:
                    continue
                seen_provider_ids.add(provider_id)

                business = {
                    "provider_id": provider_id,
                    "business_name": name,
                    "category": category.replace("_", " ").title(),
                    "address": address or "Address unavailable",
                    "city": city,
                    "state": state,
                    "country": country,
                    "website": website,
                    "phone": phone,
                    "email": email,
                    "email_available": bool(email),
                    "source": "openstreetmap",
                    "contact_source": None,
                    "relevance_score": 0,
                }
                unique_businesses.append(business)
            break

        if not request_succeeded:
            buyer_type = query.strip().lower()
            photon_tags = PHOTON_TAGS_BY_BUYER_TYPE.get(
                buyer_type,
                PHOTON_TAGS_BY_BUYER_TYPE["other"],
            )
            for osm_tag in photon_tags:
                params = {
                    "lat": latitude,
                    "lon": longitude,
                    "radius": 50,
                    "limit": limit,
                    "osm_tag": osm_tag,
                }
                logger.info("Attempting Photon reverse search for OSM tag %s", osm_tag)
                try:
                    async with httpx.AsyncClient(
                        timeout=8.0,
                        headers={"User-Agent": PHOTON_USER_AGENT},
                    ) as client:
                        response = await client.get(PHOTON_REVERSE_URL, params=params)
                except (httpx.HTTPError, TimeoutError) as exc:
                    logger.warning(
                        "Photon reverse search for %s failed with %s: %s",
                        osm_tag,
                        type(exc).__name__,
                        exc,
                        exc_info=True,
                    )
                    continue

                if response.status_code != 200:
                    logger.warning(
                        "Photon reverse search for %s returned HTTP status %s",
                        osm_tag,
                        response.status_code,
                    )
                    continue

                try:
                    photon_payload = response.json()
                except ValueError as exc:
                    logger.warning("Photon returned invalid JSON for %s: %s", osm_tag, exc, exc_info=True)
                    continue

                if not isinstance(photon_payload, dict) or not isinstance(photon_payload.get("features"), list):
                    logger.warning("Photon returned an invalid response for %s", osm_tag)
                    continue

                request_succeeded = True
                for feature in photon_payload["features"]:
                    if not isinstance(feature, dict):
                        continue
                    properties = feature.get("properties")
                    if not isinstance(properties, dict):
                        continue
                    name = normalize_name(properties.get("name"))
                    osm_type = properties.get("osm_type")
                    osm_id = properties.get("osm_id")
                    if not name or not osm_type or osm_id is None:
                        continue
                    house_number = properties.get("housenumber")
                    street = properties.get("street")
                    address = " ".join(filter(None, [house_number, street])) or None
                    website = extract_osm_website(properties)
                    phone = properties.get("phone") or properties.get("contact:phone")
                    email = properties.get("email") or properties.get("contact:email")
                    business = {
                        "provider_id": f"osm:{osm_type}:{osm_id}",
                        "business_name": name,
                        "category": str(
                            properties.get("osm_value")
                            or properties.get("osm_key")
                            or properties.get("type")
                            or "Business"
                        ).replace("_", " ").title(),
                        "address": address,
                        "city": properties.get("city"),
                        "state": properties.get("state"),
                        "country": properties.get("country"),
                        "website": website,
                        "phone": phone,
                        "email": email,
                        "email_available": bool(email),
                        "source": "openstreetmap",
                        "contact_source": None,
                        "relevance_score": 0,
                    }
                    unique_businesses.append(business)

        if not unique_businesses:
            if request_succeeded:
                logger.info("Buyer search returned no matching businesses for query %s", query)
                return []
            raise RuntimeError(
                "All configured OpenStreetMap Overpass endpoints failed. Check Render logs for details."
            )

        deduped = deduplicate_businesses(unique_businesses)
        scored = []
        scoring_context = " ".join(
            filter(
                None,
                [
                    query,
                    location.get("product_category"),
                    location.get("product_description"),
                ],
            )
        )
        keywords = [
            piece.lower()
            for piece in re.findall(r"[A-Za-z]+", scoring_context.lower())
            if len(piece) > 2
        ]
        for business in deduped:
            business["relevance_score"] = score_business(business, query, keywords)
            scored.append(business)

        scored.sort(key=lambda row: row.get("relevance_score", 0), reverse=True)
        return scored[:limit]
