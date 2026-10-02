from __future__ import annotations

import logging
import math
import re
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


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


def deduplicate_businesses(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    deduped: list[dict] = []
    for item in rows:
        business_name = (item.get("business_name") or "").strip().lower()
        website = (item.get("website") or "").lower().strip()
        phone = (item.get("phone") or "").lower().strip()
        address_key = f"{business_name}|{(item.get('address') or '').strip().lower()}"
        signature = (
            item.get("provider_id")
            or website
            or phone
            or address_key
            or f"{business_name}|{item.get('city') or ''}|{item.get('state') or ''}"
        )
        if not signature:
            continue
        if signature in seen:
            continue
        seen.add(signature)
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

    south, west, north, east = [float(value) for value in bbox]
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
    tag_clause = ";\n".join([f"nwr[{tag}]({south},{west},{north},{east});" for tag in tags])
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
        south, west, north, east = [float(value) for value in bbox]
        return build_overpass_query_for_bbox(buyer_type, (south, west, north, east), limit)

    radius = max(800, min(3000, int(limit * 250)))
    tags = get_supported_tags(buyer_type)
    tag_clause = ";\n".join([f"nwr[{tag}](around:{radius},{lat},{lon});" for tag in tags])
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
        self.api_url = api_url or settings.OVERPASS_API_URL
        self.user_agent = user_agent or settings.OVERPASS_USER_AGENT

    async def search(self, query: str, location: dict[str, Any] | str, limit: int):
        if isinstance(location, str):
            raise ValueError("A resolved location is required before using the Overpass provider.")

        latitude = location.get("latitude")
        longitude = location.get("longitude")
        if latitude is None or longitude is None:
            raise ValueError("Location resolution did not produce usable coordinates.")

        bbox = location.get("boundingbox") or []
        if len(bbox) == 4:
            tiles = split_bbox_into_tiles(bbox)
            if len(tiles) > 1:
                logger.info("Overpass buyer search using %s tiles for %s at %s", len(tiles), query, location.get("display_name"))
            else:
                tiles = [tuple(float(value) for value in bbox)]
        else:
            tiles = [(float(latitude), float(longitude), float(latitude), float(longitude))]

        unique_businesses: list[dict] = []
        seen_provider_ids: set[str] = set()
        tiles_attempted = 0
        failed_tiles: list[str] = []

        def process_tiles(tile_set: list[tuple[float, float, float, float]], label: str) -> bool:
            nonlocal unique_businesses, seen_provider_ids, tiles_attempted, failed_tiles
            for tile_index, tile in enumerate(tile_set, start=1):
                tiles_attempted += 1
                tile_label = f"{label} tile {tile_index}/{len(tile_set)}"
                tile_query = build_overpass_query_for_bbox(query, tile, limit=max(8, min(limit, 25)))
                logger.info("Overpass request %s: %s", tile_label, tile)

                try:
                    async with httpx.AsyncClient(timeout=25.0, headers={"User-Agent": self.user_agent}) as client:
                        response = await client.post(self.api_url, data=tile_query)
                except httpx.RequestError as exc:
                    failed_tiles.append(tile_label)
                    logger.warning("Overpass request failed for %s: %s", tile_label, exc, exc_info=True)
                    continue

                if response.status_code in {429, 503}:
                    failed_tiles.append(tile_label)
                    logger.warning("Overpass request returned %s for %s", response.status_code, tile_label)
                    return False
                if response.status_code >= 500:
                    failed_tiles.append(tile_label)
                    logger.warning("Overpass server error %s for %s", response.status_code, tile_label)
                    return False
                if response.status_code != 200:
                    failed_tiles.append(tile_label)
                    logger.warning("Overpass request status %s for %s", response.status_code, tile_label)
                    continue

                try:
                    payload = response.json()
                except ValueError as exc:
                    failed_tiles.append(tile_label)
                    logger.warning("Overpass returned non-JSON for %s: %s", tile_label, exc, exc_info=True)
                    continue

                if isinstance(payload, dict) and isinstance(payload.get("remark"), str):
                    remark = payload.get("remark", "")
                    if "timeout" in remark.lower():
                        failed_tiles.append(tile_label)
                        logger.warning("Overpass query timed out for %s: %s", tile_label, remark)
                        continue

                nodes = payload.get("elements", [])
                for element in nodes:
                    tags = element.get("tags") or {}
                    name = normalize_name(tags.get("name") or tags.get("brand")) or "Business name unavailable"
                    category = tags.get("shop") or tags.get("craft") or tags.get("amenity") or "Business"
                    address = tags.get("addr:street")
                    city = tags.get("addr:city") or location.get("city")
                    state = tags.get("addr:state") or location.get("state")
                    country = tags.get("addr:country") or "United States"
                    website = tags.get("website") or tags.get("contact:website")
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

                if len(unique_businesses) >= limit:
                    return True

            return False

        process_tiles(tiles, "primary")

        if not unique_businesses:
            if failed_tiles:
                logger.warning("All Overpass tiles failed for query %s: %s", query, failed_tiles)
            raise RuntimeError("We couldn't retrieve buyer results right now. Please try again.")

        deduped = deduplicate_businesses(unique_businesses)
        scored = []
        keywords = [piece.lower() for piece in re.findall(r"[A-Za-z]+", query.lower()) if len(piece) > 2]
        for business in deduped:
            business["relevance_score"] = score_business(business, query, keywords)
            scored.append(business)

        scored.sort(key=lambda row: row.get("relevance_score", 0), reverse=True)
        return scored[:limit]
