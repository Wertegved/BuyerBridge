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
PHOTON_FORWARD_URL = "https://photon.komoot.io/api/"
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
        "shop:decor",
    ),
    "interior architecture firms": (
        "craft:interior_design",
        "office:interior_design",
        "shop:furniture",
        "shop:home_furniture",
        "shop:interior_decoration",
        "shop:decor",
    ),
    "furniture stores": (
        "shop:furniture",
        "shop:home_furniture",
    ),
    "home decor stores": (
        "shop:decor",
        "shop:interior_decoration",
        "shop:gift",
        "shop:home_furniture",
        "shop:furniture",
    ),
    "home furnishing retailers": (
        "shop:home_furniture",
        "shop:furniture",
        "shop:decor",
        "shop:interior_decoration",
    ),
    "home staging companies": (
        "craft:interior_design",
        "office:interior_design",
        "shop:furniture",
        "shop:home_furniture",
        "shop:interior_decoration",
    ),
    "gift/home stores": (
        "shop:gift",
        "shop:decor",
        "shop:home_furniture",
        "shop:furniture",
    ),
    "gift & home stores": (
        "shop:gift",
        "shop:decor",
        "shop:home_furniture",
        "shop:furniture",
    ),
    "boutique home stores": (
        "shop:decor",
        "shop:gift",
        "shop:home_furniture",
        "shop:furniture",
        "shop:interior_decoration",
    ),
    "other": (
        "shop:furniture",
        "shop:home_furniture",
        "shop:decor",
        "shop:gift",
        "shop:interior_decoration",
        "craft:interior_design",
        "office:interior_design",
    ),
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


def extract_osm_tag(tags: dict[str, Any], fields: tuple[str, ...]) -> str | None:
    for field in fields:
        value = normalize_name(tags.get(field))
        if value:
            return value

    osm_tags = tags.get("osm_tags")
    if isinstance(osm_tags, dict):
        for field in fields:
            value = normalize_name(osm_tags.get(field))
            if value:
                return value
    elif isinstance(osm_tags, list):
        for item in osm_tags:
            if isinstance(item, dict) and item.get("key") in fields:
                value = normalize_name(item.get("value"))
                if value:
                    return value

    return None


def extract_osm_website(tags: dict[str, Any]) -> str | None:
    return extract_osm_tag(tags, ("website", "contact:website", "url", "contact:url"))


def _merge_osm_metadata(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    for field, value in (
        ("website", extract_osm_website(source)),
        ("contact:website", source.get("contact:website") or source.get("website")),
        ("url", source.get("url") or source.get("contact:url")),
        ("contact:url", source.get("contact:url") or source.get("url")),
        ("email", extract_osm_tag(source, ("email", "contact:email"))),
        ("contact:email", source.get("contact:email") or source.get("email")),
        ("phone", extract_osm_tag(source, ("phone", "contact:phone"))),
        ("contact:phone", source.get("contact:phone") or source.get("phone")),
        ("address", source.get("address") or source.get("addr:street") or source.get("street")),
        ("city", source.get("city") or source.get("town") or source.get("village")),
        ("state", source.get("state") or source.get("county") or source.get("province")),
        ("country", source.get("country") or source.get("country_code")),
    ):
        if value is None:
            continue
        if field in {"website", "url", "email", "phone", "address", "city", "state", "country"}:
            current = target.get(field)
            if current in (None, ""):
                target[field] = value
        elif field.startswith("contact:"):
            primary_key = field.split(":", 1)[1]
            current = target.get(primary_key)
            if current in (None, ""):
                target[primary_key] = value
        else:
            current = target.get(field)
            if current in (None, ""):
                target[field] = value
    if "website" in target and target["website"] in (None, ""):
        target["website"] = target.get("contact:website") or target.get("url") or target.get("contact:url")
    if "email" in target and target["email"] in (None, ""):
        target["email"] = target.get("contact:email")
    if "phone" in target and target["phone"] in (None, ""):
        target["phone"] = target.get("contact:phone")
    return target


def normalize_osm_ref(osm_type: Any, osm_id: Any) -> str | None:
    if osm_id is None:
        return None

    raw_type = str(osm_type or "").strip().upper()
    if raw_type in {"NODE", "N"}:
        prefix = "N"
    elif raw_type in {"WAY", "W"}:
        prefix = "W"
    elif raw_type in {"RELATION", "REL", "R"}:
        prefix = "R"
    else:
        raw_value = str(osm_id).strip().upper()
        if raw_value and raw_value[0] in {"N", "W", "R"} and raw_value[1:].isdigit():
            return raw_value
        return None

    raw_id = str(osm_id).strip()
    if raw_id.startswith(prefix):
        normalized = raw_id
    else:
        normalized = f"{prefix}{raw_id.lstrip('-') if raw_id.startswith('-') else raw_id}"

    if normalized[1:].isdigit():
        return normalized
    return None


async def lookup_osm_metadata_by_ids(osm_refs: list[tuple[str, int]]) -> dict[str, dict[str, Any]]:
    if not osm_refs:
        return {}

    collected: dict[str, dict[str, Any]] = {}
    lookup_ids = []
    for osm_type, osm_id in osm_refs:
        lookup_ref = normalize_osm_ref(osm_type, osm_id)
        if lookup_ref:
            lookup_ids.append(lookup_ref)

    for index in range(0, len(lookup_ids), 50):
        batch = lookup_ids[index : index + 50]
        params = {
            "format": "jsonv2",
            "addressdetails": 1,
            "extratags": 1,
            "namedetails": 1,
            "osm_ids": ",".join(batch),
        }
        try:
            async with httpx.AsyncClient(timeout=12.0, headers={"User-Agent": PHOTON_USER_AGENT}) as client:
                if not hasattr(client, "get"):
                    logger.warning("Nominatim lookup client does not support GET requests.")
                    continue
                response = await client.get("https://nominatim.openstreetmap.org/lookup", params=params)
        except (AttributeError, httpx.HTTPError, TimeoutError) as exc:
            logger.warning("Nominatim lookup failed: %s", exc, exc_info=True)
            continue

        if response.status_code != 200:
            logger.warning("Nominatim lookup returned HTTP status %s", response.status_code)
            continue

        try:
            payload = response.json()
        except ValueError as exc:
            logger.warning("Nominatim lookup returned invalid JSON: %s", exc, exc_info=True)
            continue

        if not isinstance(payload, list):
            continue

        for item in payload:
            if not isinstance(item, dict):
                continue
            lookup_key = normalize_osm_ref(item.get("osm_type") or item.get("type") or "", item.get("osm_id") or item.get("id"))
            if not lookup_key:
                continue
            collected[lookup_key] = item

    return collected


async def hydrate_osm_metadata(businesses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    osm_refs: list[tuple[str, int]] = []
    for business in businesses:
        osm_ref = business.get("_osm_ref")
        if not isinstance(osm_ref, tuple) or len(osm_ref) != 2 or osm_ref[1] is None:
            continue
        osm_refs.append((str(osm_ref[0]), int(osm_ref[1])))

    if not osm_refs:
        return businesses

    osms_by_id = await lookup_osm_metadata_by_ids(osm_refs)
    for business in businesses:
        osm_ref = business.get("_osm_ref")
        if not isinstance(osm_ref, tuple) or len(osm_ref) != 2:
            continue
        lookup_key = normalize_osm_ref(osm_ref[0], osm_ref[1])
        if not lookup_key:
            continue
        matching = osms_by_id.get(lookup_key)
        if not isinstance(matching, dict):
            continue

        extratags = matching.get("extratags") or {}
        address = matching.get("address") or {}
        metadata_source = {
            "website": business.get("website") or matching.get("website") or extratags.get("website") or extratags.get("contact:website") or matching.get("url") or extratags.get("url") or extratags.get("contact:url"),
            "contact:website": extratags.get("contact:website") or matching.get("contact:website") or extratags.get("website") or matching.get("website"),
            "url": matching.get("url") or extratags.get("url") or extratags.get("contact:url"),
            "contact:url": extratags.get("contact:url") or matching.get("contact:url") or extratags.get("url") or matching.get("url"),
            "email": business.get("email") or matching.get("email") or extratags.get("email") or extratags.get("contact:email"),
            "contact:email": extratags.get("contact:email") or matching.get("contact:email") or matching.get("email") or extratags.get("email"),
            "phone": business.get("phone") or matching.get("phone") or extratags.get("phone") or extratags.get("contact:phone"),
            "contact:phone": extratags.get("contact:phone") or matching.get("contact:phone") or matching.get("phone") or extratags.get("phone"),
            "address": business.get("address") or address.get("road") or address.get("house_number") or matching.get("display_name"),
            "city": business.get("city") or address.get("city") or address.get("town") or address.get("village"),
            "state": business.get("state") or address.get("state") or address.get("province"),
            "country": business.get("country") or address.get("country") or address.get("country_code"),
        }
        _merge_osm_metadata(business, metadata_source)
        if business.get("email"):
            business["email_available"] = True
            business["contact_source"] = "openstreetmap"
        if business.get("address") in (None, "", "Address unavailable"):
            display_name = matching.get("display_name")
            if isinstance(display_name, str):
                business["address"] = display_name.split(",")[0].strip() or business.get("address")

    for business in businesses:
        business.pop("_osm_ref", None)
    return businesses


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


STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "your",
    "company",
    "business",
    "inc",
    "llc",
    "ltd",
}


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_keyword_tokens(value: Any) -> list[str]:
    text = normalize_text(value)
    if not text:
        return []

    tokens: list[str] = []
    for token in text.split():
        if len(token) <= 2:
            continue
        cleaned = token.rstrip("s") if token.endswith("s") and not token.endswith("ss") else token
        if cleaned in STOP_WORDS:
            continue
        tokens.append(cleaned)
    return tokens


def overlap_score(left: list[str], right: list[str]) -> float:
    if not left or not right:
        return 0.0
    left_set = set(left)
    right_set = set(right)
    if not left_set or not right_set:
        return 0.0
    overlap = len(left_set & right_set)
    union = len(left_set | right_set)
    if union == 0:
        return 0.0
    return overlap / union


def score_business(business: dict, buyer_type: str, product_keywords: list[str]) -> int:
    buyer_terms = normalize_keyword_tokens(buyer_type)
    business_name = normalize_text(business.get("business_name"))
    category_text = normalize_text(business.get("category"))
    address_text = normalize_text(business.get("address"))
    city_text = normalize_text(business.get("city"))
    state_text = normalize_text(business.get("state"))
    requested_city = normalize_text(business.get("requested_city") or business.get("city"))
    requested_state = normalize_text(business.get("requested_state"))
    product_terms = normalize_keyword_tokens(" ".join(product_keywords))
    name_tokens = normalize_keyword_tokens(business_name)
    category_tokens = normalize_keyword_tokens(category_text)
    business_terms = normalize_keyword_tokens(f"{business_name} {category_text} {address_text}")

    score = 0

    buyer_match = 0.0
    if buyer_terms:
        buyer_match = max(
            overlap_score(buyer_terms, category_tokens),
            overlap_score(buyer_terms, name_tokens),
        )
        if category_text and any(term in category_text for term in buyer_terms):
            buyer_match = max(buyer_match, 1.0)
        if buyer_terms and business_name and set(buyer_terms).issubset(set(name_tokens)):
            buyer_match = max(buyer_match, 0.9)
    score += int(round(35 * buyer_match))

    product_match = overlap_score(product_terms, business_terms)
    score += int(round(20 * product_match))

    keyword_match = overlap_score(
        product_terms,
        normalize_keyword_tokens(f"{business_name} {category_text} {address_text} {city_text} {state_text}"),
    )
    score += int(round(15 * keyword_match))

    name_match = overlap_score(product_terms, name_tokens) if product_terms else 0.0
    score += int(round(10 * name_match))

    if requested_city and city_text:
        if city_text == requested_city:
            score += 10
        elif requested_state and state_text == requested_state:
            score += 3

    if business.get("website"):
        score += 5
    if business.get("email"):
        score += 5

    return max(0, min(score, 100))


def get_supported_tags(buyer_type: str) -> list[str]:
    normalized = (buyer_type or "").strip().lower()
    tags = PHOTON_TAGS_BY_BUYER_TYPE.get(normalized, PHOTON_TAGS_BY_BUYER_TYPE["other"])
    deduped: list[str] = []
    for tag in tags:
        if tag not in deduped:
            deduped.append(tag)
    return deduped


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
    max_results = min(max(int(limit), 1), 50)
    query = f"""
    [out:json][timeout:12];
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

    radius = 15000
    tags = get_supported_tags(buyer_type)
    tag_clause = "\n".join([f"nwr[{tag}](around:{radius},{lat},{lon});" for tag in tags])
    max_results = min(max(int(limit), 1), 50)
    query = f"""
    [out:json][timeout:12];
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

        overpass_query = build_overpass_query(query, location, limit)
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
                phone = extract_osm_tag(tags, ("phone", "contact:phone"))
                email = extract_osm_tag(tags, ("email", "contact:email"))

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
                    "_osm_ref": (str(element.get("type") or "node"), int(element.get("id"))),
                }
                unique_businesses.append(business)
            break

        if not request_succeeded:
            buyer_type = query.strip().lower()
            photon_tags = PHOTON_TAGS_BY_BUYER_TYPE.get(
                buyer_type,
                PHOTON_TAGS_BY_BUYER_TYPE["other"],
            )
            bbox = location.get("boundingbox") or []
            photon_limit = min(max(int(limit), 1), 50)
            for osm_tag in photon_tags:
                params = {
                    "q": query,
                    "lat": latitude,
                    "lon": longitude,
                    "limit": photon_limit,
                    "osm_tag": osm_tag,
                    "countrycode": "US",
                }
                if len(bbox) == 4:
                    params["bbox"] = f"{bbox[2]},{bbox[0]},{bbox[3]},{bbox[1]}"
                logger.info("Attempting Photon forward search for OSM tag %s", osm_tag)
                try:
                    async with httpx.AsyncClient(
                        timeout=8.0,
                        headers={"User-Agent": PHOTON_USER_AGENT},
                    ) as client:
                        response = await client.get(PHOTON_FORWARD_URL, params=params)
                except (httpx.HTTPError, TimeoutError) as exc:
                    logger.warning(
                        "Photon forward search for %s failed with %s: %s",
                        osm_tag,
                        type(exc).__name__,
                        exc,
                        exc_info=True,
                    )
                    continue

                if response.status_code != 200:
                    logger.warning(
                        "Photon forward search for %s returned HTTP status %s",
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

                    geometry = feature.get("geometry") if isinstance(feature.get("geometry"), dict) else {}
                    coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
                    if len(bbox) == 4 and isinstance(coordinates, (list, tuple)) and len(coordinates) >= 2:
                        try:
                            feature_lon = float(coordinates[0])
                            feature_lat = float(coordinates[1])
                        except (TypeError, ValueError):
                            continue
                        south, north, west, east = [float(value) for value in bbox]
                        if not (south <= feature_lat <= north and west <= feature_lon <= east):
                            continue

                    house_number = properties.get("housenumber")
                    street = properties.get("street")
                    address = " ".join(filter(None, [house_number, street])) or None
                    website = extract_osm_website(properties)
                    phone = extract_osm_tag(properties, ("phone", "contact:phone"))
                    email = extract_osm_tag(properties, ("email", "contact:email"))
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
                        "city": properties.get("city") or location.get("city"),
                        "state": properties.get("state") or location.get("state"),
                        "country": properties.get("country") or location.get("country") or "United States",
                        "website": website,
                        "phone": phone,
                        "email": email,
                        "email_available": bool(email),
                        "source": "openstreetmap",
                        "contact_source": None,
                        "relevance_score": 0,
                        "_osm_ref": (str(osm_type), int(osm_id)),
                    }
                    unique_businesses.append(business)

        if not unique_businesses:
            if request_succeeded:
                logger.info("Buyer search returned no matching businesses for query %s", query)
                return []
            raise RuntimeError(
                "All configured OpenStreetMap Overpass endpoints failed. Check Render logs for details."
            )

        unique_businesses = await hydrate_osm_metadata(unique_businesses)
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
            business["requested_city"] = location.get("city") or location.get("display_name")
            business["requested_state"] = location.get("state")
            business["relevance_score"] = score_business(business, query, keywords)
            scored.append(business)

        scored.sort(key=lambda row: (-int(row.get("relevance_score", 0)), -int(bool(row.get("requested_city") and normalize_name(row.get("city")) == normalize_name(row.get("requested_city")))), str(row.get("business_name") or "")))
        return scored[: min(max(int(limit), 1), 50)]
