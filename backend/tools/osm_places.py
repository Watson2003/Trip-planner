from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Iterable
from typing import Any

import httpx

from data.destination_fallbacks import DESTINATION_ALIASES, DESTINATION_CENTER_COORDS
from utils.config import settings


logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
)


def normalize_place_name(name: str) -> str:
    text = str(name or "").strip().casefold()
    if not text:
        return ""
    text = text.replace("&", " and ")
    text = re.sub(r"[\u2018\u2019`']", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    prefixes = (
        "visit to ",
        "visit ",
        "explore ",
        "discover ",
        "see ",
        "hotel ",
        "restaurant ",
        "cafe ",
        "breakfast at ",
        "breakfast near ",
        "check in at ",
        "check-in at ",
        "lunch at ",
        "lunch near ",
        "dinner at ",
        "dinner near ",
        "restaurant at ",
        "hotel at ",
        "guest house at ",
        "guest house ",
        "guesthouse ",
        "guest_house ",
        "resort at ",
        "resort ",
        "stay at ",
        "stay ",
        "lodge at ",
        "lodge ",
        "at ",
    )
    stripped = text.strip()
    while True:
        updated = stripped
        for prefix in prefixes:
            if updated.startswith(prefix):
                updated = updated[len(prefix) :].strip()
                break
        if updated == stripped:
            break
        stripped = updated
    return re.sub(r"\s+", " ", stripped).strip()


def classify_osm_place(tags: dict[str, Any]) -> str:
    tags = tags or {}
    tourism = str(tags.get("tourism") or "").strip().casefold()
    amenity = str(tags.get("amenity") or "").strip().casefold()
    leisure = str(tags.get("leisure") or "").strip().casefold()
    natural = str(tags.get("natural") or "").strip().casefold()
    historic = str(tags.get("historic") or "").strip().casefold()
    shop = str(tags.get("shop") or "").strip().casefold()

    if tourism in {"hotel", "guest_house", "resort"}:
        return tourism
    if tourism in {"museum", "viewpoint", "attraction", "gallery", "theme_park"}:
        return tourism
    if amenity in {"restaurant", "cafe"}:
        return amenity
    if leisure == "park":
        return "park"
    if natural in {"peak", "waterfall", "lake", "beach"}:
        return natural
    if historic:
        return "historic"
    if shop == "mall":
        return "mall"
    return tourism or amenity or leisure or natural or historic or shop or "attraction"


def _best_time_for_category(category: str) -> str:
    category = (category or "").casefold()
    if category in {"hotel", "guest_house", "resort"}:
        return "Anytime"
    if category in {"restaurant", "cafe"}:
        return "Breakfast / Lunch / Dinner"
    if category in {"museum", "historic"}:
        return "Morning"
    if category in {"viewpoint", "peak", "waterfall", "lake", "park", "attraction"}:
        return "Morning / Evening"
    if category == "mall":
        return "Evening"
    return "Morning"


def _estimated_duration(category: str) -> int:
    category = (category or "").casefold()
    if category in {"restaurant", "cafe"}:
        return 60
    if category in {"hotel", "guest_house", "resort"}:
        return 30
    if category in {"museum", "historic"}:
        return 75
    if category in {"viewpoint", "peak"}:
        return 90
    if category in {"waterfall", "lake", "park", "attraction"}:
        return 100
    if category == "mall":
        return 120
    return 60


def _nominatim_headers() -> dict[str, str]:
    return {
        "User-Agent": settings.osm_user_agent or "RoadMindAI/1.0",
        "Accept": "application/json",
    }


def _fallback_geocode_location(location: str) -> dict[str, Any] | None:
    normalized = normalize_place_name(location)
    if not normalized:
        return None

    aliases = dict(DESTINATION_ALIASES)
    canonical = aliases.get(normalized)
    if canonical is None:
        for alias, mapped in sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True):
            if alias and alias in normalized:
                canonical = mapped
                break

    if not canonical:
        return None

    coords = DESTINATION_CENTER_COORDS.get(canonical)
    if not coords:
        return None

    return {
        "latitude": float(coords[0]),
        "longitude": float(coords[1]),
        "display_name": location,
        "osm_type": "",
        "osm_id": "",
        "tags": {},
    }


async def geocode_location(location: str) -> dict[str, Any] | None:
    location = str(location or "").strip()
    if not location:
        return None

    params = {
        "q": location,
        "format": "jsonv2",
        "limit": 1,
        "addressdetails": 1,
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0), headers=_nominatim_headers()) as client:
            response = await client.get(NOMINATIM_URL, params=params)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("Nominatim geocoding failed for %s: %s", location, exc)
        return _fallback_geocode_location(location)

    if not isinstance(payload, list) or not payload:
        return _fallback_geocode_location(location)

    first = payload[0]
    if not isinstance(first, dict):
        return _fallback_geocode_location(location)

    lat = first.get("lat")
    lon = first.get("lon")
    if lat is None or lon is None:
        return _fallback_geocode_location(location)

    return {
        "latitude": float(lat),
        "longitude": float(lon),
        "display_name": str(first.get("display_name") or location),
        "osm_type": str(first.get("osm_type") or ""),
        "osm_id": str(first.get("osm_id") or ""),
        "tags": first.get("address") or {},
    }


def _overpass_query(lat: float, lon: float, radius_m: int) -> str:
    return f"""
[out:json][timeout:35];
(
  node(around:{radius_m},{lat},{lon})["tourism"~"attraction|museum|viewpoint|gallery|theme_park|hotel|guest_house|resort"];
  way(around:{radius_m},{lat},{lon})["tourism"~"attraction|museum|viewpoint|gallery|theme_park|hotel|guest_house|resort"];
  relation(around:{radius_m},{lat},{lon})["tourism"~"attraction|museum|viewpoint|gallery|theme_park|hotel|guest_house|resort"];
  node(around:{radius_m},{lat},{lon})["amenity"~"restaurant|cafe"];
  way(around:{radius_m},{lat},{lon})["amenity"~"restaurant|cafe"];
  relation(around:{radius_m},{lat},{lon})["amenity"~"restaurant|cafe"];
  node(around:{radius_m},{lat},{lon})["leisure"="park"];
  way(around:{radius_m},{lat},{lon})["leisure"="park"];
  relation(around:{radius_m},{lat},{lon})["leisure"="park"];
  node(around:{radius_m},{lat},{lon})["natural"~"peak|waterfall|lake|beach"];
  way(around:{radius_m},{lat},{lon})["natural"~"peak|waterfall|lake|beach"];
  relation(around:{radius_m},{lat},{lon})["natural"~"peak|waterfall|lake|beach"];
  node(around:{radius_m},{lat},{lon})["historic"];
  way(around:{radius_m},{lat},{lon})["historic"];
  relation(around:{radius_m},{lat},{lon})["historic"];
  node(around:{radius_m},{lat},{lon})["shop"="mall"];
  way(around:{radius_m},{lat},{lon})["shop"="mall"];
  relation(around:{radius_m},{lat},{lon})["shop"="mall"];
);
out center tags;
""".strip()


def _element_lat_lon(element: dict[str, Any]) -> tuple[float | None, float | None]:
    if "lat" in element and "lon" in element:
        try:
            return float(element.get("lat")), float(element.get("lon"))
        except (TypeError, ValueError):
            return None, None
    center = element.get("center")
    if isinstance(center, dict):
        try:
            return float(center.get("lat")), float(center.get("lon"))
        except (TypeError, ValueError):
            return None, None
    return None, None


def _format_address(tags: dict[str, Any], fallback: str) -> str:
    pieces = [
        str(tags.get("addr:housename") or "").strip(),
        str(tags.get("addr:housenumber") or "").strip(),
        str(tags.get("addr:street") or "").strip(),
        str(tags.get("addr:suburb") or "").strip(),
        str(tags.get("addr:city") or "").strip(),
    ]
    address = ", ".join(piece for piece in pieces if piece)
    if address:
        return address
    return str(tags.get("addr:full") or fallback or "").strip()


def _convert_element(element: dict[str, Any], destination: str, index: int) -> dict[str, Any] | None:
    tags = element.get("tags") or {}
    if not isinstance(tags, dict):
        return None

    lat, lon = _element_lat_lon(element)
    if lat is None or lon is None:
        return None

    name = str(tags.get("name") or tags.get("brand") or "").strip()
    if not name:
        return None

    category = classify_osm_place(tags)
    osm_type = str(element.get("type") or tags.get("osm_type") or "").strip()
    osm_id = str(element.get("id") or tags.get("osm_id") or index).strip()
    address = _format_address(tags, destination)

    return {
        "name": name,
        "category": category,
        "latitude": float(lat),
        "longitude": float(lon),
        "address": address or destination,
        "osm_type": osm_type,
        "osm_id": osm_id,
        "place_id": f"osm-{osm_type or 'element'}-{osm_id}",
        "tags": tags,
        "estimated_duration_minutes": _estimated_duration(category),
        "best_time_to_visit": _best_time_for_category(category),
    }


def deduplicate_places(places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for place in places:
        if not isinstance(place, dict):
            continue
        name = normalize_place_name(str(place.get("name") or ""))
        lat = place.get("latitude")
        lon = place.get("longitude")
        coord_key = ""
        try:
            if lat is not None and lon is not None:
                coord_key = f"{float(lat):.4f}:{float(lon):.4f}"
        except (TypeError, ValueError):
            coord_key = ""
        key = name or coord_key
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(place)
    return unique


async def fetch_osm_places(destination: str, radius_km: int = 15) -> list[dict[str, Any]]:
    destination = str(destination or "").strip()
    if not destination:
        return []

    geocoded = await geocode_location(destination)
    if not geocoded:
        return []

    radius_m = max(1000, int(radius_km * 1000))
    query = _overpass_query(geocoded["latitude"], geocoded["longitude"], radius_m)

    payload: dict[str, Any] | None = None
    last_error: Exception | None = None
    for overpass_url in OVERPASS_URLS:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(25.0), headers=_nominatim_headers()) as client:
                response = await client.post(overpass_url, data=query.encode("utf-8"))
                response.raise_for_status()
                candidate = response.json()
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            last_error = exc
            logger.warning("Overpass fetch failed for %s via %s: %s", destination, overpass_url, exc)
            continue

        elements = candidate.get("elements") if isinstance(candidate, dict) else None
        if isinstance(elements, list):
            payload = candidate
            if elements:
                break
            # Empty results may be valid, but if another endpoint can answer, try it.
            continue

    if payload is None:
        if last_error:
            logger.warning("All Overpass endpoints failed for %s: %s", destination, last_error)
        return []

    elements = payload.get("elements") if isinstance(payload, dict) else None
    if not isinstance(elements, list):
        return []

    places: list[dict[str, Any]] = []
    for index, element in enumerate(elements):
        if not isinstance(element, dict):
            continue
        converted = _convert_element(element, destination, index)
        if converted:
            places.append(converted)

    deduped = deduplicate_places(places)
    logger.info(
        "[OSM] destination=%s fetched=%d deduped=%d radius_km=%s",
        destination,
        len(places),
        len(deduped),
        radius_km,
    )
    logger.info(
        "[OSM] counts attractions=%d restaurants=%d hotels=%d scenic=%d",
        sum(1 for place in deduped if classify_osm_place(place.get("tags", {})) not in {"restaurant", "cafe", "hotel", "guest_house", "resort"}),
        sum(1 for place in deduped if classify_osm_place(place.get("tags", {})) in {"restaurant", "cafe"}),
        sum(1 for place in deduped if classify_osm_place(place.get("tags", {})) in {"hotel", "guest_house", "resort"}),
        sum(1 for place in deduped if classify_osm_place(place.get("tags", {})) in {"viewpoint", "peak", "waterfall", "lake", "park", "museum", "historic"}),
    )
    return deduped


def _to_thread_result(destination: str, radius_km: int) -> list[dict[str, Any]]:
    return asyncio.run(fetch_osm_places(destination=destination, radius_km=radius_km))
