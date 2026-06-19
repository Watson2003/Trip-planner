from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

from tools.osm_places import classify_osm_place, fetch_osm_places, normalize_place_name
from utils.destination_places import build_destination_place_pools, validate_destination_places
from utils.places import price_level_estimate_inr, price_level_to_inr


logger = logging.getLogger(__name__)

TARGET_COUNTS = {
    "hotel": 7,
    "restaurant": 8,
    "attraction": 12,
}


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _fallback_coordinates(destination: str) -> tuple[float, float]:
    coords = {
        "ooty": (11.4102, 76.6950),
        "trichy": (10.7905, 78.7047),
        "tiruchirappalli": (10.7905, 78.7047),
        "bengaluru": (12.9716, 77.5946),
        "bangalore": (12.9716, 77.5946),
        "coimbatore": (11.0168, 76.9558),
        "chennai": (13.0827, 80.2707),
    }
    key = _normalize_text(destination).casefold()
    if key in coords:
        return coords[key]

    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    lat_offset = (int(digest[:4], 16) % 3000) / 1000 - 1.5
    lng_offset = (int(digest[4:8], 16) % 3000) / 1000 - 1.5
    return 20.5937 + lat_offset, 78.9629 + lng_offset


def _title_case_category(kind: str) -> str:
    return {"hotel": "Hotel", "restaurant": "Restaurant", "attraction": "Attraction"}.get(kind, kind.title())


def _osm_kind(place: dict[str, Any]) -> str | None:
    tags = place.get("tags") if isinstance(place.get("tags"), dict) else {}
    category = _normalize_text(place.get("category")).casefold()
    tourism = _normalize_text(tags.get("tourism")).casefold()
    amenity = _normalize_text(tags.get("amenity")).casefold()
    leisure = _normalize_text(tags.get("leisure")).casefold()
    natural = _normalize_text(tags.get("natural")).casefold()
    historic = _normalize_text(tags.get("historic")).casefold()

    if category in {"hotel", "guest_house", "resort"} or tourism in {"hotel", "guest_house", "resort"} or amenity == "hotel":
        return "hotel"
    if category in {"restaurant", "cafe"} or amenity in {"restaurant", "cafe"}:
        return "restaurant"
    if tourism in {"attraction", "museum", "viewpoint"}:
        return "attraction"
    if leisure == "park" or natural in {"peak", "waterfall", "lake"} or historic:
        return "attraction"
    return None


def _extract_osm_description(place: dict[str, Any], kind: str, destination: str) -> str:
    description = _normalize_text(place.get("description"))
    if description:
        return description

    tags = place.get("tags") if isinstance(place.get("tags"), dict) else {}
    best_time = _normalize_text(place.get("best_time_to_visit") or tags.get("opening_hours"))
    if kind == "hotel":
        return f"Comfortable stay in {destination} with easy access to the main route."
    if kind == "restaurant":
        cuisine = _normalize_text(tags.get("cuisine") or place.get("cuisine"))
        if cuisine:
            return f"{cuisine} dining stop in {destination} with quick access for travelers."
        return f"Handy dining stop in {destination} for a road trip break."
    if best_time:
        return f"Popular sightseeing stop in {destination}. Best time to visit: {best_time}."
    return f"Popular sightseeing stop in {destination}."


def _coordinates_with_offset(destination: str, index: int) -> tuple[float, float]:
    lat, lng = _fallback_coordinates(destination)
    return lat + (index * 0.006), lng + (index * 0.006)


def _map_osm_place(place: dict[str, Any], destination: str, kind: str, index: int) -> dict[str, Any]:
    tags = place.get("tags") if isinstance(place.get("tags"), dict) else {}
    lat = place.get("latitude")
    lng = place.get("longitude")
    if lat is None or lng is None:
        lat, lng = _coordinates_with_offset(destination, index)

    name = _normalize_text(place.get("name"))
    if not name:
        name = f"{destination} {_title_case_category(kind)} {index + 1}"

    address = _normalize_text(place.get("address")) or _normalize_text(tags.get("addr:full")) or destination
    description = _extract_osm_description(place, kind, destination)
    rating = float(place.get("rating") or 4.2)
    total_reviews = int(place.get("total_reviews") or 90)
    place_id = _normalize_text(place.get("place_id")) or f"osm-{kind}-{normalize_place_name(name) or index + 1}"
    maps_url = f"https://www.openstreetmap.org/search?query={name.replace(' ', '+')}"

    if kind == "hotel":
        price_level = 2 if _normalize_text(tags.get("tourism")).casefold() == "hotel" else 1
        return {
            "place_id": place_id,
            "name": name,
            "description": description,
            "address": address,
            "rating": rating,
            "total_reviews": total_reviews,
            "price_range": price_level_to_inr(price_level, "hotel"),
            "price_level": price_level,
            "photo_url": None,
            "lat": float(lat),
            "lng": float(lng),
            "latitude": float(lat),
            "longitude": float(lng),
            "maps_url": maps_url,
            "website": _normalize_text(tags.get("website")) or None,
            "phone": _normalize_text(tags.get("phone") or tags.get("contact:phone")) or None,
            "open_now": None,
            "category": "Mid-range" if price_level >= 2 else "Budget",
            "estimated_cost_inr": price_level_estimate_inr(price_level, "hotel"),
        }

    if kind == "restaurant":
        price_level = 1 if _normalize_text(tags.get("amenity")).casefold() == "cafe" else 2
        cuisine = _normalize_text(tags.get("cuisine")).replace("_", " ").title() or (
            "Cafe" if _normalize_text(tags.get("amenity")).casefold() == "cafe" else "Multi Cuisine"
        )
        return {
            "place_id": place_id,
            "name": name,
            "description": description,
            "address": address,
            "rating": rating,
            "total_reviews": total_reviews,
            "price_range": price_level_to_inr(price_level, "restaurant"),
            "price_level": price_level,
            "photo_url": None,
            "lat": float(lat),
            "lng": float(lng),
            "latitude": float(lat),
            "longitude": float(lng),
            "maps_url": maps_url,
            "website": _normalize_text(tags.get("website")) or None,
            "phone": _normalize_text(tags.get("phone") or tags.get("contact:phone")) or None,
            "open_now": None,
            "cuisine": cuisine,
            "category": "Both",
            "estimated_cost_inr": price_level_estimate_inr(price_level, "restaurant"),
        }

    entry_level = 0 if _normalize_text(tags.get("natural")).casefold() in {"peak", "waterfall", "lake"} else 1
    return {
        "place_id": place_id,
        "name": name,
        "description": description,
        "address": address,
        "rating": rating,
        "total_reviews": total_reviews,
        "entry_fee": price_level_to_inr(entry_level, "attraction"),
        "price_level": entry_level,
        "photo_url": None,
        "lat": float(lat),
        "lng": float(lng),
        "latitude": float(lat),
        "longitude": float(lng),
        "maps_url": maps_url,
        "website": _normalize_text(tags.get("website")) or None,
        "phone": _normalize_text(tags.get("phone") or tags.get("contact:phone")) or None,
        "open_now": None,
        "type": _normalize_text(place.get("category")) or "Attraction",
        "entry_fee_inr": price_level_estimate_inr(entry_level, "attraction"),
    }


def _catalog_from_items(destination: str, items: dict[str, list[dict[str, Any]]], fallback_generated: bool) -> dict[str, Any]:
    return {
        "destination": destination,
        "hotels": items.get("hotel", []),
        "restaurants": items.get("restaurant", []),
        "attractions": items.get("attraction", []),
        "fallback_generated": fallback_generated,
    }


def _dedupe_by_name(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        name = normalize_place_name(item.get("name", ""))
        key = name or _normalize_text(item.get("place_id"))
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _sort_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            -float(item.get("rating") or 0.0),
            -int(item.get("total_reviews") or 0),
            normalize_place_name(item.get("name", "")),
        ),
    )


def _pool_item_to_entry(destination: str, kind: str, index: int, item: dict[str, Any]) -> dict[str, Any]:
    lat, lng = _coordinates_with_offset(destination, index)
    name = _normalize_text(item.get("name")) or f"{destination} {_title_case_category(kind)} {index + 1}"
    description = _normalize_text(item.get("description"))
    if not description:
        if kind == "hotel":
            description = f"A practical stay in {destination} for travelers looking for a reliable base."
        elif kind == "restaurant":
            description = f"A dependable dining stop in {destination} with easy access for road trippers."
        else:
            description = f"A popular sightseeing stop in {destination} that works well for a road trip."

    if kind == "hotel":
        price_level = (index % 4) + 1
        return {
            "place_id": f"fallback-{normalize_place_name(destination)}-hotel-{index + 1}",
            "name": name,
            "description": description,
            "address": destination,
            "rating": float(4.8 - (index * 0.1)),
            "total_reviews": 210 - (index * 10),
            "price_range": price_level_to_inr(price_level, "hotel"),
            "price_level": price_level,
            "photo_url": None,
            "lat": lat,
            "lng": lng,
            "latitude": lat,
            "longitude": lng,
            "maps_url": f"https://www.google.com/maps/search/?api=1&query={name.replace(' ', '+')}+{destination.replace(' ', '+')}",
            "website": None,
            "phone": None,
            "open_now": None,
            "category": "Budget" if price_level == 1 else "Mid-range",
            "estimated_cost_inr": price_level_estimate_inr(price_level, "hotel"),
        }

    if kind == "restaurant":
        price_level = (index % 4) + 1
        cuisines = ["South Indian", "Multi Cuisine", "Cafe", "Indian"]
        cuisine = cuisines[index % len(cuisines)]
        return {
            "place_id": f"fallback-{normalize_place_name(destination)}-restaurant-{index + 1}",
            "name": name,
            "description": description,
            "address": destination,
            "rating": float(4.7 - (index * 0.1)),
            "total_reviews": 260 - (index * 12),
            "price_range": price_level_to_inr(price_level, "restaurant"),
            "price_level": price_level,
            "photo_url": None,
            "lat": lat,
            "lng": lng,
            "latitude": lat,
            "longitude": lng,
            "maps_url": f"https://www.google.com/maps/search/?api=1&query={name.replace(' ', '+')}+{destination.replace(' ', '+')}",
            "website": None,
            "phone": None,
            "open_now": None,
            "cuisine": cuisine,
            "category": "Both",
            "estimated_cost_inr": price_level_estimate_inr(price_level, "restaurant"),
        }

    price_level = 0 if index < 4 else 1
    return {
        "place_id": f"fallback-{normalize_place_name(destination)}-attraction-{index + 1}",
        "name": name,
        "description": description,
        "address": destination,
        "rating": float(4.9 - (index * 0.05)),
        "total_reviews": 180 - (index * 8),
        "entry_fee": price_level_to_inr(price_level, "attraction"),
        "price_level": price_level,
        "photo_url": None,
        "lat": lat,
        "lng": lng,
        "latitude": lat,
        "longitude": lng,
        "maps_url": f"https://www.google.com/maps/search/?api=1&query={name.replace(' ', '+')}+{destination.replace(' ', '+')}",
        "website": None,
        "phone": None,
        "open_now": None,
        "type": _normalize_text(item.get("type")) or "Attraction",
        "entry_fee_inr": price_level_estimate_inr(price_level, "attraction"),
    }


async def build_destination_recommendations(destination: str) -> dict[str, Any]:
    destination = _normalize_text(destination)
    if not destination:
        return {
            "destination": "",
            "hotels": [],
            "restaurants": [],
            "attractions": [],
            "fallback_generated": False,
        }

    fallback_generated = False
    try:
        # Keep trip planning responsive. If OSM is slow, we fall back to deterministic pools.
        osm_places = await asyncio.wait_for(fetch_osm_places(destination, radius_km=15), timeout=5.0)
    except Exception as exc:
        logger.warning("OSM recommendation fetch failed for %s: %s", destination, exc)
        osm_places = []

    buckets: dict[str, list[dict[str, Any]]] = {"hotel": [], "restaurant": [], "attraction": []}
    for index, place in enumerate(osm_places):
        if not isinstance(place, dict):
            continue
        kind = _osm_kind(place)
        if not kind:
            continue
        buckets[kind].append(_map_osm_place(place, destination, kind, index))

    for kind in buckets:
        buckets[kind] = _sort_items(_dedupe_by_name(validate_destination_places(destination, buckets[kind])))[: TARGET_COUNTS[kind]]

    missing = {kind: max(0, TARGET_COUNTS[kind] - len(buckets[kind])) for kind in buckets}
    if any(missing.values()):
        fallback_pools = build_destination_place_pools(destination, include_llm=True)
        for kind in buckets:
            source_items = list(fallback_pools.get(f"{kind}s", []))
            for item in source_items:
                if len(buckets[kind]) >= TARGET_COUNTS[kind]:
                    break
                buckets[kind].append(_pool_item_to_entry(destination, kind, len(buckets[kind]), item))
            fallback_generated = True

    for kind in buckets:
        if len(buckets[kind]) < TARGET_COUNTS[kind]:
            fallback_pools = build_destination_place_pools(destination, include_llm=True)
            for item in fallback_pools.get(f"{kind}s", []):
                if len(buckets[kind]) >= TARGET_COUNTS[kind]:
                    break
                buckets[kind].append(_pool_item_to_entry(destination, kind, len(buckets[kind]), item))
            fallback_generated = True

        buckets[kind] = validate_destination_places(destination, _sort_items(_dedupe_by_name(buckets[kind])))[: TARGET_COUNTS[kind]]

    catalog = _catalog_from_items(destination, buckets, fallback_generated)
    print(f"Recommendations for {destination}")
    print(f"Hotels: {len(catalog['hotels'])}")
    print(f"Restaurants: {len(catalog['restaurants'])}")
    print(f"Attractions: {len(catalog['attractions'])}")
    logger.info(
        "Recommendations for %s | Hotels: %d | Restaurants: %d | Attractions: %d",
        destination,
        len(catalog["hotels"]),
        len(catalog["restaurants"]),
        len(catalog["attractions"]),
    )
    return catalog
