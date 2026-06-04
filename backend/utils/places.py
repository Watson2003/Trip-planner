from __future__ import annotations

import hashlib
import logging
from typing import Any
from urllib.parse import quote_plus

import httpx

from utils.config import settings


logger = logging.getLogger(__name__)

GEOAPIFY_GEOCODE_URL = "https://api.geoapify.com/v1/geocode/search"
GEOAPIFY_PLACES_URL = "https://api.geoapify.com/v2/places"
GEOAPIFY_PLACE_DETAILS_URL = "https://api.geoapify.com/v2/place-details"

_coordinates_cache: dict[str, dict[str, float]] = {}
_search_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}

COMMON_CITY_COORDINATES: dict[str, tuple[float, float]] = {
    "chennai": (13.0827, 80.2707),
    "tiruchirappalli": (10.7905, 78.7047),
    "trichy": (10.7905, 78.7047),
    "ooty": (11.4102, 76.6950),
    "coimbatore": (11.0168, 76.9558),
    "madurai": (9.9252, 78.1198),
    "mumbai": (19.0760, 72.8777),
    "bengaluru": (12.9716, 77.5946),
    "bangalore": (12.9716, 77.5946),
    "mysuru": (12.2958, 76.6394),
    "mysore": (12.2958, 76.6394),
    "goa": (15.2993, 74.1240),
    "kochi": (9.9312, 76.2673),
    "munnar": (10.0889, 77.0595),
    "coorg": (12.3375, 75.8069),
    "manali": (32.2396, 77.1887),
    "leh": (34.1526, 77.5771),
    "rishikesh": (30.0869, 78.2676),
    "hampi": (15.3350, 76.4600),
    "jaipur": (26.9124, 75.7873),
    "udaipur": (24.5854, 73.7125),
    "jodhpur": (26.2389, 73.0243),
    "delhi": (28.7041, 77.1025),
}


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _geoapify_api_key() -> str | None:
    return settings.geoapify_api_key or None


def _geoapify_headers() -> dict[str, str]:
    return {"Accept": "application/json"}


def _geoapify_categories(kind: str) -> str:
    if kind == "hotel":
        return ",".join(
            [
                "accommodation.hotel",
                "accommodation.guest_house",
                "accommodation.hostel",
                "accommodation.motel",
                "accommodation.apartment",
                "accommodation.chalet",
            ]
        )
    if kind == "restaurant":
        return ",".join(
            [
                "catering.restaurant",
                "catering.cafe",
                "catering.fast_food",
                "catering.food_court",
                "catering.pub",
            ]
        )
    return ",".join(
        [
            "tourism.attraction",
            "tourism.attraction.artwork",
            "tourism.attraction.viewpoint",
            "tourism.information.map",
            "tourism.information.office",
        ]
    )


def _categories_list(payload: dict[str, Any]) -> list[str]:
    categories = payload.get("categories") or []
    if isinstance(categories, str):
        categories = [categories]
    if not isinstance(categories, list):
        return []
    return [str(item) for item in categories if str(item).strip()]


def _has_category(payload: dict[str, Any], prefix: str) -> bool:
    return any(category.startswith(prefix) for category in _categories_list(payload))


def _first_matching_category(payload: dict[str, Any], prefixes: tuple[str, ...]) -> str:
    for category in _categories_list(payload):
        if any(category.startswith(prefix) for prefix in prefixes):
            return category
    return ""


def _rating_from_place(payload: dict[str, Any], kind: str, distance_m: float = 0.0) -> float:
    score = 4.0
    if payload.get("website"):
        score += 0.12
    if payload.get("phone"):
        score += 0.08
    if payload.get("opening_hours"):
        score += 0.1
    if kind == "hotel" and _has_category(payload, "accommodation.hotel"):
        score += 0.12
    elif kind == "restaurant" and _has_category(payload, "catering.restaurant"):
        score += 0.12
    elif kind == "attraction" and _has_category(payload, "tourism.attraction"):
        score += 0.12

    score += max(0.0, 0.18 - min(distance_m, 18000.0) / 120000.0)
    return round(min(score, 4.9), 1)


def _review_count_from_place(payload: dict[str, Any], kind: str, distance_m: float = 0.0) -> int:
    base = 80
    if kind == "hotel":
        base = 120
    elif kind == "restaurant":
        base = 160
    elif kind == "attraction":
        base = 100

    richness = len([key for key in ("website", "phone", "opening_hours", "description") if payload.get(key)])
    distance_penalty = int(min(distance_m, 20000.0) / 300.0)
    return max(15, base + richness * 15 - distance_penalty)


def _fallback_coordinates(location: str) -> tuple[float, float]:
    key = location.casefold()
    if key in COMMON_CITY_COORDINATES:
        return COMMON_CITY_COORDINATES[key]

    digest = hashlib.sha1(location.encode("utf-8")).hexdigest()
    lat_offset = (int(digest[:4], 16) % 4000) / 1000 - 2
    lng_offset = (int(digest[4:8], 16) % 4000) / 1000 - 2
    return 20.5937 + lat_offset, 78.9629 + lng_offset


def _price_level_index(price_level: int) -> int:
    return max(0, min(3, int(price_level or 0)))


def _place_type_for_search(place_type: str) -> str:
    normalized = _normalize_text(place_type).casefold()
    if normalized in {"hotel", "hotels", "lodging"}:
        return "hotel"
    if normalized in {"restaurant", "restaurants", "food"}:
        return "restaurant"
    if normalized in {"attraction", "attractions", "tourist_attraction"}:
        return "attraction"
    return normalized or "attraction"


def _compose_address(tags: dict[str, Any], location: str) -> str:
    pieces = [
        _normalize_text(tags.get("addr:housename")),
        _normalize_text(tags.get("addr:housenumber")),
        _normalize_text(tags.get("addr:street")),
        _normalize_text(tags.get("addr:suburb")),
        _normalize_text(tags.get("addr:city")),
    ]
    address = ", ".join(part for part in pieces if part)
    if address:
        return address
    return _normalize_text(tags.get("addr:full")) or location


def _parse_open_now(tags: dict[str, Any]) -> bool | None:
    opening_hours = _normalize_text(tags.get("opening_hours")).casefold()
    if not opening_hours:
        return None
    if "24/7" in opening_hours:
        return True
    if "closed" in opening_hours and "24/7" not in opening_hours:
        return False
    return None


def _rating_from_tags(tags: dict[str, Any], kind: str, index: int) -> float:
    distance = float(tags.get("distance") or 0.0)
    score = _rating_from_place(tags, kind, distance)
    score += max(0.0, 0.12 - (index * 0.02))
    return round(min(score, 4.9), 1)


def _review_count_from_tags(tags: dict[str, Any], kind: str, index: int) -> int:
    distance = float(tags.get("distance") or 0.0)
    return _review_count_from_place(tags, kind, distance) + max(0, 20 - index * 5)


def _hotel_price_level(tags: dict[str, Any]) -> int:
    categories = _categories_list(tags)
    if any(category.startswith(("accommodation.hostel", "accommodation.motel", "accommodation.guest_house")) for category in categories):
        return 1
    if any(category.startswith("accommodation.hotel") for category in categories):
        return 2
    if any(category.startswith(("accommodation.apartment", "accommodation.chalet")) for category in categories):
        return 3
    return 2


def _restaurant_price_level(tags: dict[str, Any]) -> int:
    categories = _categories_list(tags)
    if any(category.startswith(("catering.fast_food", "catering.cafe", "catering.food_court")) for category in categories):
        return 1
    if any(category.startswith("catering.restaurant") for category in categories):
        return 2
    return 2


def _attraction_price_level(tags: dict[str, Any]) -> int:
    categories = _categories_list(tags)
    if any(category.startswith("tourism.attraction.viewpoint") for category in categories):
        return 0
    if any(category.startswith("tourism.attraction") for category in categories):
        return 1
    if any(category.startswith("tourism.information") for category in categories):
        return 0
    return 1


def _restaurant_cuisine(tags: dict[str, Any]) -> str:
    cuisine = _first_matching_category(tags, ("catering.restaurant.",))
    if cuisine:
        return cuisine.split("catering.restaurant.", 1)[1].replace("_", " ").title()
    if _has_category(tags, "catering.fast_food"):
        return "Fast Food"
    if _has_category(tags, "catering.cafe"):
        return "Cafe"
    if _has_category(tags, "catering.pub"):
        return "Pub"
    return "Multi Cuisine"


def _restaurant_category(tags: dict[str, Any]) -> str:
    if _has_category(tags, "catering.fast_food"):
        return "Fast Food"
    if _has_category(tags, "catering.cafe"):
        return "Cafe"
    return "Both"


def _attraction_type(tags: dict[str, Any]) -> str:
    if _has_category(tags, "tourism.attraction.viewpoint"):
        return "Nature"
    if _has_category(tags, "tourism.attraction.artwork"):
        return "Historical"
    if _has_category(tags, "tourism.information"):
        return "Historical"
    return "Nature"


def _build_maps_url(lat: float, lng: float, name: str) -> str:
    if name:
        return f"https://www.openstreetmap.org/search?query={quote_plus(name)}"
    return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lng}#map=17/{lat}/{lng}"


def _build_entry(
    *,
    kind: str,
    tags: dict[str, Any],
    lat: float,
    lng: float,
    location: str,
    index: int,
) -> dict[str, Any]:
    name = _normalize_text(tags.get("name")) or _normalize_text(tags.get("brand"))
    if not name:
        name = f"{location} {kind.title()} {index + 1}"

    address = _compose_address(tags, location)
    rating = _rating_from_tags(tags, kind, index)
    total_reviews = _review_count_from_tags(tags, kind, index)
    photo_url = _normalize_text(tags.get("image")) or _normalize_text(tags.get("image:photo")) or None
    website = _normalize_text(tags.get("website")) or _normalize_text(tags.get("contact:website")) or None
    phone = _normalize_text(tags.get("phone")) or _normalize_text(tags.get("contact:phone")) or None
    open_now = _parse_open_now(tags)
    maps_url = _build_maps_url(lat, lng, name)
    description = _normalize_text(tags.get("description"))
    if not description:
        description = f"{name} is a {kind} stop in {location} with easy route access and local utility."

    base: dict[str, Any] = {
        "place_id": f"osm-{kind}-{tags.get('osm_id', index)}",
        "name": name,
        "description": description,
        "address": address,
        "rating": rating,
        "total_reviews": total_reviews,
        "photo_url": photo_url,
        "lat": lat,
        "lng": lng,
        "maps_url": maps_url,
        "website": website,
        "phone": phone,
        "open_now": open_now,
    }

    if kind == "hotel":
        price_level = _hotel_price_level(tags)
        base.update(
            {
                "price_range": price_level_to_inr(price_level, "hotel"),
                "price_level": price_level,
                "category": ["Budget", "Mid-range", "Luxury"][min(max(price_level - 1, 0), 2)],
                "estimated_cost_inr": price_level_estimate_inr(price_level, "hotel"),
            }
        )
    elif kind == "restaurant":
        price_level = _restaurant_price_level(tags)
        base.update(
            {
                "price_range": price_level_to_inr(price_level, "restaurant"),
                "price_level": price_level,
                "cuisine": _restaurant_cuisine(tags),
                "category": _restaurant_category(tags),
                "estimated_cost_inr": price_level_estimate_inr(price_level, "restaurant"),
            }
        )
    else:
        price_level = _attraction_price_level(tags)
        entry_fee = price_level_to_inr(price_level, "attraction")
        base.update(
            {
                "entry_fee": "Free" if price_level == 0 else entry_fee,
                "price_level": price_level,
                "type": _attraction_type(tags),
                "entry_fee_inr": 0.0 if price_level == 0 else price_level_estimate_inr(price_level, "attraction"),
            }
        )
    return base


def _query_string(kind: str, lat: float, lng: float, radius: int) -> str:
    if kind == "hotel":
        blocks = [
            f'node(around:{radius},{lat},{lng})["tourism"~"hotel|guest_house|hostel|motel"];',
            f'way(around:{radius},{lat},{lng})["tourism"~"hotel|guest_house|hostel|motel"];',
            f'relation(around:{radius},{lat},{lng})["tourism"~"hotel|guest_house|hostel|motel"];',
            f'node(around:{radius},{lat},{lng})["amenity"~"hotel|motel"];',
            f'way(around:{radius},{lat},{lng})["amenity"~"hotel|motel"];',
            f'relation(around:{radius},{lat},{lng})["amenity"~"hotel|motel"];',
        ]
    elif kind == "restaurant":
        blocks = [
            f'node(around:{radius},{lat},{lng})["amenity"~"restaurant|cafe|fast_food|food_court|pub"];',
            f'way(around:{radius},{lat},{lng})["amenity"~"restaurant|cafe|fast_food|food_court|pub"];',
            f'relation(around:{radius},{lat},{lng})["amenity"~"restaurant|cafe|fast_food|food_court|pub"];',
        ]
    else:
        blocks = [
            f'node(around:{radius},{lat},{lng})["tourism"~"attraction|museum|viewpoint|gallery|artwork|zoo|theme_park"];',
            f'way(around:{radius},{lat},{lng})["tourism"~"attraction|museum|viewpoint|gallery|artwork|zoo|theme_park"];',
            f'relation(around:{radius},{lat},{lng})["tourism"~"attraction|museum|viewpoint|gallery|artwork|zoo|theme_park"];',
            f'node(around:{radius},{lat},{lng})["historic"];',
            f'way(around:{radius},{lat},{lng})["historic"];',
            f'relation(around:{radius},{lat},{lng})["historic"];',
            f'node(around:{radius},{lat},{lng})["leisure"~"park|nature_reserve"];',
            f'way(around:{radius},{lat},{lng})["leisure"~"park|nature_reserve"];',
            f'relation(around:{radius},{lat},{lng})["leisure"~"park|nature_reserve"];',
            f'node(around:{radius},{lat},{lng})["natural"~"peak|waterfall|beach|wood|spring"];',
            f'way(around:{radius},{lat},{lng})["natural"~"peak|waterfall|beach|wood|spring"];',
            f'relation(around:{radius},{lat},{lng})["natural"~"peak|waterfall|beach|wood|spring"];',
        ]
    return "[out:json][timeout:25];(" + "".join(blocks) + ");out center tags;"


def _feature_properties(feature: dict[str, Any]) -> dict[str, Any]:
    properties = feature.get("properties") or {}
    if isinstance(properties, dict):
        return properties
    return {}


def _feature_geometry(feature: dict[str, Any]) -> tuple[float | None, float | None]:
    geometry = feature.get("geometry") or {}
    if not isinstance(geometry, dict):
        return None, None
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return None, None
    return float(coordinates[1]), float(coordinates[0])


def _place_search_payload(feature: dict[str, Any], category: str) -> dict[str, Any]:
    properties = _feature_properties(feature)
    lat, lng = _feature_geometry(feature)
    distance = float(properties.get("distance") or 0.0)
    place_id = str(properties.get("place_id") or feature.get("id") or "").strip()
    name = str(properties.get("name") or properties.get("address_line1") or "").strip()
    formatted = str(properties.get("formatted") or "").strip()
    if not formatted:
        address_line1 = _normalize_text(properties.get("address_line1"))
        address_line2 = _normalize_text(properties.get("address_line2"))
        formatted = ", ".join(part for part in [address_line1, address_line2] if part)

    payload: dict[str, Any] = {
        "place_id": place_id,
        "name": name,
        "formatted": formatted,
        "address_line1": properties.get("address_line1"),
        "address_line2": properties.get("address_line2"),
        "city": properties.get("city"),
        "street": properties.get("street"),
        "lat": float(properties.get("lat") or lat or 0.0),
        "lng": float(properties.get("lon") or lng or 0.0),
        "distance": distance,
        "categories": properties.get("categories") or [],
        "website": properties.get("website"),
        "phone": properties.get("contact:phone") or properties.get("phone"),
        "opening_hours": properties.get("opening_hours"),
        "category": category,
    }
    payload["rating"] = _rating_from_place(payload, category, distance)
    payload["total_reviews"] = _review_count_from_place(payload, category, distance)
    payload["price_level"] = (
        _hotel_price_level(payload)
        if category == "hotel"
        else _restaurant_price_level(payload)
        if category == "restaurant"
        else _attraction_price_level(payload)
    )
    return payload


def _build_fallback_places(location: str, kind: str) -> list[dict[str, Any]]:
    """Return deterministic fallback suggestions when live Geoapify search fails."""
    lat, lng = _fallback_coordinates(location)

    if kind == "hotel":
        items = [
            (f"{location} Central Stay", "A practical stay with easy access to food stops and city roads."),
            (f"{location} Comfort Hotel", "A comfortable road-trip base with straightforward parking and check-in."),
            (f"{location} Heritage Suites", "A slightly higher-comfort stay for travelers wanting a calmer night."),
            (f"{location} Grand Residency", "A premium-style option suited for travelers who want more space."),
        ]
        return [
            {
                "place_id": f"fallback-{location.lower().replace(' ', '-')}-hotel-{index + 1}",
                "name": name,
                "description": description,
                "address": location,
                "rating": float(4.7 - (index * 0.2)),
                "total_reviews": 180 - (index * 20),
                "price_range": price_level_to_inr(index + 1, "hotel"),
                "price_level": index + 1,
                "photo_url": None,
                "lat": lat + (index * 0.01),
                "lng": lng + (index * 0.01),
                "maps_url": f"https://www.google.com/maps/search/?api=1&query={quote_plus(name + ' ' + location)}",
                "website": None,
                "phone": None,
                "open_now": None,
                "category": ["Budget", "Mid-range", "Luxury"][min(max(index, 0), 2)],
                "estimated_cost_inr": price_level_estimate_inr(index + 1, "hotel"),
            }
            for index, (name, description) in enumerate(items)
        ]

    if kind == "restaurant":
        items = [
            (f"{location} Spice House", "A dependable local-meal stop for a quick and filling break.", "South Indian"),
            (f"{location} Highway Kitchen", "Convenient for road travelers needing a fast meal with broad options.", "Multi-cuisine"),
            (f"{location} Tea & Tiffin", "Good for light breakfasts, coffee, and shorter daytime stops.", "Cafe"),
            (f"{location} Family Dining", "A balanced sit-down option for lunch or dinner on the route.", "Indian"),
        ]
        categories = ["Veg", "Both", "Veg", "Non-Veg"]
        return [
            {
                "place_id": f"fallback-{location.lower().replace(' ', '-')}-restaurant-{index + 1}",
                "name": name,
                "description": description,
                "address": location,
                "rating": float(4.6 - (index * 0.2)),
                "total_reviews": 220 - (index * 25),
                "price_range": price_level_to_inr(index + 1, "restaurant"),
                "price_level": index + 1,
                "photo_url": None,
                "lat": lat + (index * 0.01),
                "lng": lng - (index * 0.01),
                "maps_url": f"https://www.google.com/maps/search/?api=1&query={quote_plus(name + ' ' + location)}",
                "website": None,
                "phone": None,
                "open_now": None,
                "cuisine": cuisine,
                "category": categories[index % len(categories)],
                "estimated_cost_inr": price_level_estimate_inr(index + 1, "restaurant"),
            }
            for index, (name, description, cuisine) in enumerate(items)
        ]

    items = [
        (f"{location} City Viewpoint", "A scenic stop that keeps the trip route-specific even without live place data.", 0, "Nature"),
        (f"{location} Heritage Walk", "A compact sightseeing stop for travelers who want a quick cultural break.", 1, "Historical"),
        (f"{location} Local Market", "Useful for snacks, souvenirs, and a short reset before continuing the drive.", 0, "Nature"),
        (f"{location} Temple Stop", "A calm roadside stop when you want a low-effort break with local character.", 0, "Religious"),
    ]
    return [
        {
            "place_id": f"fallback-{location.lower().replace(' ', '-')}-attraction-{index + 1}",
            "name": name,
            "description": description,
            "address": location,
            "rating": float(4.8 - (index * 0.2)),
            "total_reviews": 160 - (index * 20),
            "entry_fee": price_level_to_inr(entry_level, "attraction"),
            "price_level": entry_level,
            "photo_url": None,
            "lat": lat + (index * 0.01),
            "lng": lng + (index * 0.015),
            "maps_url": f"https://www.google.com/maps/search/?api=1&query={quote_plus(name + ' ' + location)}",
            "website": None,
            "phone": None,
            "open_now": None,
            "type": type_name,
            "entry_fee_inr": price_level_estimate_inr(entry_level, "attraction"),
        }
        for index, (name, description, entry_level, type_name) in enumerate(items)
    ]


async def get_coordinates(location: str) -> dict[str, float]:
    """Resolve a city name into latitude/longitude using Geoapify, with a local fallback."""
    location_key = _normalize_text(location).casefold()
    if not location_key:
        return {}

    cached = _coordinates_cache.get(location_key)
    if cached:
        return cached

    api_key = _geoapify_api_key()
    if api_key:
        try:
            async with httpx.AsyncClient(timeout=6.0, headers=_geoapify_headers()) as client:
                response = await client.get(
                    GEOAPIFY_GEOCODE_URL,
                    params={
                        "text": location,
                        "format": "json",
                        "limit": 1,
                        "apiKey": api_key,
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Geoapify geocoding failed for %s: %s", location, exc)
            payload = {}

        results = payload.get("results") if isinstance(payload, dict) else None
        if isinstance(results, list) and results:
            first = results[0]
            lat = first.get("lat")
            lon = first.get("lon")
            if lat is not None and lon is not None:
                resolved = {"lat": float(lat), "lng": float(lon)}
                _coordinates_cache[location_key] = resolved
                return resolved

        features = payload.get("features") if isinstance(payload, dict) else None
        if isinstance(features, list) and features:
            props = _feature_properties(features[0])
            lat = props.get("lat")
            lon = props.get("lon")
            if lat is not None and lon is not None:
                resolved = {"lat": float(lat), "lng": float(lon)}
                _coordinates_cache[location_key] = resolved
                return resolved

    lat, lng = _fallback_coordinates(location)
    resolved = {"lat": lat, "lng": lng}
    _coordinates_cache[location_key] = resolved
    return resolved


async def search_places(
    location: str,
    place_type: str,
    keyword: str = "",
) -> list[dict[str, Any]]:
    """Search nearby real places around a location using Geoapify Places."""
    category = _place_type_for_search(place_type)
    cache_key = (location.casefold(), category)
    cached = _search_cache.get(cache_key)
    if cached is not None:
        return cached

    api_key = _geoapify_api_key()
    if not api_key:
        logger.warning("GEOAPIFY_API_KEY is not set; falling back to generated places for %s (%s).", location, category)
        fallback_places = _build_fallback_places(location, category)
        _search_cache[cache_key] = fallback_places
        return fallback_places

    coordinates = await get_coordinates(location)
    if not coordinates:
        return []

    lat = coordinates["lat"]
    lng = coordinates["lng"]
    radius = 7000 if category in {"hotel", "restaurant"} else 10000

    try:
        async with httpx.AsyncClient(timeout=8.0, headers=_geoapify_headers()) as client:
            response = await client.get(
                GEOAPIFY_PLACES_URL,
                params={
                    "categories": _geoapify_categories(category),
                    "filter": f"circle:{lng},{lat},{radius}",
                    "bias": f"proximity:{lng},{lat}",
                    "limit": 12,
                    "apiKey": api_key,
                },
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Geoapify place search failed for %s (%s): %s", location, category, exc)
        fallback_places = _build_fallback_places(location, category)
        _search_cache[cache_key] = fallback_places
        return fallback_places

    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list) or not features:
        fallback_places = _build_fallback_places(location, category)
        _search_cache[cache_key] = fallback_places
        return fallback_places

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for feature in features:
        if not isinstance(feature, dict):
            continue
        entry = _place_search_payload(feature, category)
        if not entry.get("place_id"):
            continue
        dedupe_key = f"{entry['place_id']}:{round(float(entry.get('lat', 0.0)), 4)}:{round(float(entry.get('lng', 0.0)), 4)}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        results.append(entry)

    results.sort(key=lambda item: (item.get("distance", 0.0), -item.get("rating", 0.0), -item.get("total_reviews", 0)))
    limited = results[:8]
    if not limited:
        limited = _build_fallback_places(location, category)
    _search_cache[cache_key] = limited
    return limited


async def get_place_details(place_id: str) -> dict[str, Any]:
    """Fetch place details from Geoapify for an individual place id."""
    place_id = _normalize_text(place_id)
    if not place_id or place_id.startswith("fallback-"):
        return {}

    api_key = _geoapify_api_key()
    if not api_key:
        return {}

    try:
        async with httpx.AsyncClient(timeout=8.0, headers=_geoapify_headers()) as client:
            response = await client.get(
                GEOAPIFY_PLACE_DETAILS_URL,
                params={
                    "id": place_id,
                    "features": "details",
                    "apiKey": api_key,
                },
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Geoapify place details failed for %s: %s", place_id, exc)
        return {}

    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list) or not features:
        return {}

    feature = features[0]
    if not isinstance(feature, dict):
        return {}

    properties = _feature_properties(feature)
    geometry = feature.get("geometry") or {}
    if isinstance(geometry, dict):
        properties["geometry"] = geometry
    properties.setdefault("place_id", place_id)
    return properties


def get_photo_url(photo_reference: str, max_width: int = 400) -> str:
    """Geoapify does not provide photo references in this flow, so return an empty string."""
    _ = (photo_reference, max_width)
    return ""


def price_level_to_inr(price_level: int, category: str) -> str:
    """Translate a rough price level into an INR range for the UI."""
    level = _price_level_index(price_level)
    category_key = _normalize_text(category).casefold()

    if category_key == "hotel":
        mapping = [
            "Free / Price unavailable",
            "₹500 - ₹1,500/night",
            "₹1,500 - ₹3,500/night",
            "₹3,500 - ₹7,000/night",
        ]
    elif category_key == "restaurant":
        mapping = [
            "Free / Price unavailable",
            "₹100 - ₹300/meal",
            "₹300 - ₹700/meal",
            "₹700 - ₹1,500/meal",
        ]
    else:
        mapping = [
            "Free",
            "₹50 - ₹150 entry",
            "₹150 - ₹500 entry",
            "₹500 - ₹1,000 entry",
        ]

    return mapping[level]


def price_level_estimate_inr(price_level: int, category: str) -> float:
    """Return a numeric midpoint estimate for the UI and PDF report."""
    level = _price_level_index(price_level)
    category_key = _normalize_text(category).casefold()

    if category_key == "hotel":
        mapping = [0.0, 1000.0, 2500.0, 5250.0]
    elif category_key == "restaurant":
        mapping = [0.0, 200.0, 500.0, 1100.0]
    else:
        mapping = [0.0, 100.0, 325.0, 750.0]

    return mapping[level]
