from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from agents.state import TripState
from tools.osm_places import normalize_place_name
from utils.mcp_bridge import mcp_generate_pdf_report, mcp_search_places
from utils.config import settings
from utils.destination_places import validate_destination_places
from utils.recommendations import build_destination_recommendations
from utils.places import (
    clear_cache,
    get_place_details,
    get_photo_url,
    price_level_estimate_inr,
    price_level_to_inr,
    search_places as local_search_places,
)


logger = logging.getLogger(__name__)

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

ATTRACTION_FALLBACKS: dict[str, list[tuple[str, str, int, int, str]]] = {
    "chennai": [
        ("Marina Beach", "Iconic seaside stretch for sunset walks and a breezy city break.", 0, 4, "Beach"),
        ("Kapaleeshwarar Temple", "A classic heritage stop with colorful Dravidian architecture.", 50, 4, "Religious"),
        ("Fort St. George", "Historic fort complex that anchors Chennai's colonial-era past.", 100, 4, "Historical"),
        ("Government Museum", "A compact indoor stop for art, history, and a short rest from the heat.", 40, 4, "Historical"),
    ],
    "tiruchirappalli": [
        (
            "Sri Ranganathaswamy Temple",
            "A major temple complex and one of the region's strongest cultural landmarks.",
            0,
            5,
            "Religious",
        ),
        ("Rockfort Temple", "A hilltop climb with broad city views and a quick cultural stop.", 20, 4, "Historical"),
        ("Jambukeswarar Temple", "A serene temple stop known for its water-linked sacred atmosphere.", 0, 4, "Religious"),
        ("Kallanai Dam", "A historic river engineering stop that works well as a scenic break.", 0, 4, "Nature"),
    ],
    "trichy": [
        (
            "Sri Ranganathaswamy Temple",
            "A major temple complex and one of the region's strongest cultural landmarks.",
            0,
            5,
            "Religious",
        ),
        ("Rockfort Temple", "A hilltop climb with broad city views and a quick cultural stop.", 20, 4, "Historical"),
        ("Jambukeswarar Temple", "A serene temple stop known for its water-linked sacred atmosphere.", 0, 4, "Religious"),
        ("Kallanai Dam", "A historic river engineering stop that works well as a scenic break.", 0, 4, "Nature"),
    ],
    "ooty": [
        ("Ooty Lake", "A relaxed lakeside stop with easy boating and a classic hill-station feel.", 30, 4, "Nature"),
        ("Government Botanical Garden", "A low-effort sightseeing pause with well-kept gardens and plenty of shade.", 40, 4, "Nature"),
        ("Doddabetta Peak", "A high viewpoint stop for panoramic Nilgiri hills and cooler air.", 20, 5, "Nature"),
        ("Tea Museum", "A compact stop to break the drive and learn about local tea heritage.", 50, 4, "Historical"),
    ],
}


def _normalize_location(value: Any) -> str:
    return str(value or "").strip()


def _route_locations(state: TripState) -> list[str]:
    """Return unique trip cities with the destination first."""
    ordered: list[str] = []
    seen: set[str] = set()

    destination = _normalize_location(state.get("destination"))
    origin = _normalize_location(state.get("origin"))
    waypoints = state.get("waypoints", []) or []
    if not isinstance(waypoints, list):
        waypoints = [waypoints]

    for location in [destination, *waypoints, origin]:
        if not location:
            continue
        key = location.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(location)

    return ordered


def _destination_from_user_input(user_input: Any) -> str:
    text = str(user_input or "").strip()
    if not text:
        return ""

    patterns = [
        r"from\s+(.+?)\s+to\s+(.+?)(?:[.\n]|$)",
        r"road trip from\s+(.+?)\s+to\s+(.+?)(?:[.\n]|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            candidate = match.group(2).strip().strip(".,;:")
            if candidate:
                return candidate
    return ""


def _collect_route_locations(state: TripState) -> list[str]:
    """Return unique route locations in trip order."""
    origin = _normalize_location(state.get("origin"))
    destination = _normalize_location(state.get("destination"))
    waypoints = state.get("waypoints", []) or []
    if not isinstance(waypoints, list):
        waypoints = [waypoints]

    ordered_locations: list[str] = []
    seen: set[str] = set()
    for location in [origin, *waypoints, destination]:
        if not location:
            continue
        key = location.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered_locations.append(location)
    return ordered_locations


def _extract_summary(details: dict[str, Any], fallback: str) -> str:
    editorial = details.get("editorial_summary")
    if isinstance(editorial, dict):
        summary = str(editorial.get("overview") or "").strip()
        if summary:
            return summary
    return fallback


def _first_photo_url(details: dict[str, Any]) -> str | None:
    print(f"[PLACES] Getting details for: {details.get('place_id', '')}")

    photos_list = details.get("photos", [])
    print(f"[PLACES] Photos found: {len(photos_list) if isinstance(photos_list, list) else 0}")
    if photos_list and len(photos_list) > 0:
        first_photo = photos_list[0] if isinstance(photos_list[0], dict) else {}
        photo_reference = first_photo.get("photo_reference", "")
        print(f"[PLACES] First photo_reference: {str(photo_reference)[:30]}...")
        if photo_reference:
            return get_photo_url(str(photo_reference), max_width=600)
        print(f"[PLACES] No photos available for '{details.get('name', 'unknown')}'")
        return None

    print(f"[PLACES] No photos available for '{details.get('name', 'unknown')}'")
    return None


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


def _detail_location(details: dict[str, Any], raw_place: dict[str, Any]) -> tuple[float, float]:
    geometry = details.get("geometry") or raw_place.get("geometry") or {}
    coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
    lat = details.get("lat") or raw_place.get("lat")
    lng = details.get("lng") or raw_place.get("lng")
    if lat is None and isinstance(coordinates, list) and len(coordinates) > 1:
        lat = coordinates[1]
    if lng is None and isinstance(coordinates, list) and len(coordinates) > 0:
        lng = coordinates[0]
    if lat is None or lng is None:
        lat = raw_place.get("lat", 0.0)
        lng = raw_place.get("lng", 0.0)
    return float(lat or 0.0), float(lng or 0.0)


def _price_level_category(price_level: int, kind: str) -> str:
    if kind == "hotel":
        return ["Budget", "Mid-range", "Premium", "Luxury"][min(max(price_level, 0), 3)]
    if kind == "restaurant":
        return ["Budget", "Mid-range", "Premium", "Luxury"][min(max(price_level, 0), 3)]
    return "Attraction"


def _restaurant_cuisine(details: dict[str, Any]) -> str:
    cuisine = _first_matching_category(details, ("catering.restaurant.",))
    if cuisine:
        return cuisine.split("catering.restaurant.", 1)[1].replace("_", " ").title()
    if _has_category(details, "catering.fast_food"):
        return "Fast Food"
    if _has_category(details, "catering.cafe"):
        return "Cafe"
    if _has_category(details, "catering.pub"):
        return "Pub"
    return "Restaurant"


def _attraction_type(details: dict[str, Any]) -> str:
    if _has_category(details, "tourism.attraction.viewpoint"):
        return "Nature"
    if _has_category(details, "tourism.attraction.artwork"):
        return "Historical"
    if _has_category(details, "tourism.information"):
        return "Historical"
    return "Attraction"


def _fallback_coordinates(location: str) -> tuple[float, float]:
    key = location.casefold()
    if key in COMMON_CITY_COORDINATES:
        return COMMON_CITY_COORDINATES[key]

    digest = hashlib.sha1(location.encode("utf-8")).hexdigest()
    lat_offset = (int(digest[:4], 16) % 4000) / 1000 - 2
    lng_offset = (int(digest[4:8], 16) % 4000) / 1000 - 2
    return 20.5937 + lat_offset, 78.9629 + lng_offset


def _fallback_place_id(location: str, kind: str, index: int) -> str:
    slug = "-".join(part for part in location.lower().split() if part)
    return f"fallback-{slug or 'location'}-{kind}-{index + 1}"


def _fallback_hotel_names(location: str) -> list[tuple[str, str]]:
    return [
        (f"{location} Central Stay", "A practical stay with easy access to food stops and city roads."),
        (f"{location} Comfort Hotel", "A comfortable road-trip base with straightforward parking and check-in."),
        (f"{location} Heritage Suites", "A slightly higher-comfort stay for travelers wanting a calmer night."),
        (f"{location} Grand Residency", "A premium-style option suited for travelers who want more space."),
    ]


def _fallback_restaurant_names(location: str) -> list[tuple[str, str, str]]:
    return [
        (f"{location} Spice House", "A dependable local-meal stop for a quick and filling break.", "South Indian"),
        (f"{location} Highway Kitchen", "Convenient for road travelers needing a fast meal with broad options.", "Multi-cuisine"),
        (f"{location} Tea & Tiffin", "Good for light breakfasts, coffee, and shorter daytime stops.", "Cafe"),
        (f"{location} Family Dining", "A balanced sit-down option for lunch or dinner on the route.", "Indian"),
    ]


def _fallback_attractions(location: str) -> list[tuple[str, str, int, int, str]]:
    key = location.casefold()
    if key in ATTRACTION_FALLBACKS:
        return ATTRACTION_FALLBACKS[key]
    return [
        (
            f"{location} City Viewpoint",
            "A scenic stop that keeps the trip route-specific even without live place data.",
            0,
            3,
            "Nature",
        ),
        (
            f"{location} Heritage Walk",
            "A compact sightseeing stop for travelers who want a quick cultural break.",
            30,
            3,
            "Historical",
        ),
        (
            f"{location} Local Market",
            "Useful for snacks, souvenirs, and a short reset before continuing the drive.",
            0,
            3,
            "Nature",
        ),
        (
            f"{location} Temple Stop",
            "A calm roadside stop when you want a low-effort break with local character.",
            0,
            3,
            "Religious",
        ),
    ]


def _build_common_fields(
    *,
    location: str,
    raw_place: dict[str, Any],
    details: dict[str, Any],
    kind: str,
) -> dict[str, Any]:
    merged: dict[str, Any] = {**raw_place, **details}
    place_id = str(merged.get("place_id") or "").strip()
    name = str(merged.get("name") or merged.get("address_line1") or merged.get("formatted") or "").strip()
    address = str(
        merged.get("formatted")
        or merged.get("address_line1")
        or merged.get("address_line2")
        or merged.get("city")
        or location
    ).strip()
    rating = float(merged.get("rating") or raw_place.get("rating") or 0.0)
    total_reviews = int(merged.get("total_reviews") or raw_place.get("total_reviews") or 0)
    price_level = int(merged.get("price_level") or raw_place.get("price_level") or 0)
    photos_list = details.get("photos", [])
    if photos_list and len(photos_list) > 0:
        photo_ref = photos_list[0].get("photo_reference", "")
        if photo_ref:
            photo_url = get_photo_url(photo_ref, max_width=600)
            print(f"[REC] {details.get('name')}: Photo found ✅")
        else:
            photo_url = None
            print(f"[REC] {details.get('name')}: Empty photo_reference")
    else:
        photo_url = None
        print(f"[REC] {details.get('name')}: No photos array")
    lat, lng = _detail_location(details, raw_place)
    maps_url = f"https://www.google.com/maps/search/?api=1&query={quote_plus(name + ' ' + address)}" if name or address else ""
    website = str(details.get("website") or merged.get("website") or "").strip() or None
    phone = str(details.get("phone") or details.get("contact:phone") or merged.get("phone") or "").strip() or None
    opening_hours = details.get("opening_hours") or merged.get("opening_hours") or {}
    open_now = opening_hours.get("open_now") if isinstance(opening_hours, dict) else None
    description = _extract_summary(
        details,
        f"{kind.title()} near {address or location}.",
    )

    return {
        "place_id": place_id,
        "name": name,
        "description": description,
        "address": address,
        "rating": rating,
        "total_reviews": total_reviews,
        "price_range": price_level_to_inr(price_level, kind),
        "price_level": price_level,
        "photo_url": photo_url,
        "lat": lat,
        "lng": lng,
        "maps_url": maps_url,
        "website": website,
        "phone": phone,
        "open_now": open_now,
    }


def _build_fallback_places(location: str, kind: str) -> list[dict[str, Any]]:
    lat, lng = _fallback_coordinates(location)

    if kind == "hotel":
        items = _fallback_hotel_names(location)
        return [
            {
                "place_id": _fallback_place_id(location, kind, index),
                "name": name if index < len(items) else f"{name} {index + 1}",
                "description": description,
                "address": location,
                "rating": float(4.7 - (index * 0.1)),
                "total_reviews": 180 - (index * 10),
                "price_range": price_level_to_inr((index % 4) + 1, "hotel"),
                "price_level": (index % 4) + 1,
                "photo_url": None,
                "lat": lat + (index * 0.01),
                "lng": lng + (index * 0.01),
                "maps_url": f"https://www.google.com/maps/search/?api=1&query={quote_plus(name + ' ' + location)}",
                "website": None,
                "phone": None,
                "open_now": None,
                "category": _price_level_category((index % 4) + 1, "hotel"),
                "estimated_cost_inr": price_level_estimate_inr((index % 4) + 1, "hotel"),
            }
            for index, (name, description) in enumerate((items * 3)[:10])
        ]

    if kind == "restaurant":
        items = _fallback_restaurant_names(location)
        categories = ["Veg", "Both", "Veg", "Non-Veg"]
        return [
            {
                "place_id": _fallback_place_id(location, kind, index),
                "name": name if index < len(items) else f"{name} {index + 1}",
                "description": description,
                "address": location,
                "rating": float(4.6 - (index * 0.1)),
                "total_reviews": 220 - (index * 15),
                "price_range": price_level_to_inr((index % 4) + 1, "restaurant"),
                "price_level": (index % 4) + 1,
                "photo_url": None,
                "lat": lat + (index * 0.01),
                "lng": lng - (index * 0.01),
                "maps_url": f"https://www.google.com/maps/search/?api=1&query={quote_plus(name + ' ' + location)}",
                "website": None,
                "phone": None,
                "open_now": None,
                "cuisine": cuisine,
                "category": categories[index % len(categories)],
                "estimated_cost_inr": price_level_estimate_inr((index % 4) + 1, "restaurant"),
            }
            for index, (name, description, cuisine) in enumerate((items * 3)[:10])
        ]

    items = _fallback_attractions(location)
    return [
        {
            "place_id": _fallback_place_id(location, kind, index),
            "name": name if index < len(items) else f"{name} {index + 1}",
            "description": description,
            "address": location,
            "rating": float(4.8 - (index * 0.1)),
            "total_reviews": 160 - (index * 10),
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
        for index, (name, description, entry_level, _, type_name) in enumerate((items * 3)[:10])
    ]


async def _enrich_place(location: str, raw_place: dict[str, Any], kind: str) -> dict[str, Any]:
    """Fetch place details and return a structured recommendation object."""
    place_id = str(raw_place.get("place_id") or "").strip()
    if place_id.startswith("fallback-"):
        return raw_place

    details = {
        "name": raw_place.get("name", ""),
        "formatted": raw_place.get("formatted", "") or raw_place.get("display_name", "") or raw_place.get("address_line1", ""),
        "address_line1": raw_place.get("address_line1", ""),
        "address_line2": raw_place.get("address_line2", ""),
        "rating": raw_place.get("rating", 0.0),
        "total_reviews": raw_place.get("total_reviews", 0),
        "price_level": raw_place.get("price_level", 0),
        "geometry": {"coordinates": [raw_place.get("lng", 0.0), raw_place.get("lat", 0.0)]},
        "opening_hours": {},
        "categories": raw_place.get("categories", []),
        "website": raw_place.get("website"),
        "phone": raw_place.get("phone"),
        "place_id": place_id,
    }

    try:
        detail_query = " ".join(
            part
            for part in [
                str(raw_place.get("name") or "").strip(),
                str(raw_place.get("formatted") or raw_place.get("display_name") or raw_place.get("address_line1") or location or "").strip(),
            ]
            if part
        ).strip()
        place_details = await get_place_details(place_id, query=detail_query)
        if isinstance(place_details, dict) and place_details:
            details.update(place_details)
    except Exception as exc:
        logger.warning("Failed to fetch place details for %s: %s", place_id, exc)

    common = _build_common_fields(location=location, raw_place=raw_place, details=details, kind=kind)
    if kind == "hotel":
        common.update(
            {
                "category": _price_level_category(common["price_level"], "hotel"),
                "estimated_cost_inr": price_level_estimate_inr(common["price_level"], "hotel"),
            }
        )
    elif kind == "restaurant":
        common.update(
            {
                "cuisine": _restaurant_cuisine(details),
                "category": "Both",
                "estimated_cost_inr": price_level_estimate_inr(common["price_level"], "restaurant"),
            }
        )
    else:
        common.update(
            {
                "entry_fee": price_level_to_inr(common["price_level"], "attraction"),
                "entry_fee_inr": price_level_estimate_inr(common["price_level"], "attraction"),
                "type": _attraction_type(details),
            }
        )
    return common


def _normalize_mcp_place_result(place: dict[str, Any], kind: str, index: int) -> dict[str, Any]:
    tags = place.get("tags") or {}
    if not isinstance(tags, dict):
        tags = {}

    categories = tags.get("categories") or []
    if not isinstance(categories, list):
        categories = []

    display_name = str(place.get("display_name") or place.get("name") or "").strip()
    name = str(place.get("name") or display_name.split(",")[0] or "").strip()
    place_id = str(tags.get("place_id") or place.get("place_id") or f"mcp-{kind}-{index + 1}").strip()
    price_level = int(place.get("price_level") or 0)

    return {
        "place_id": place_id,
        "name": name,
        "display_name": display_name,
        "address_line1": display_name or name,
        "address_line2": str(place.get("category") or "").strip(),
        "rating": float(place.get("rating") or 4.2),
        "total_reviews": int(place.get("total_reviews") or 0),
        "price_level": price_level,
        "lat": float(place.get("lat") or 0.0),
        "lng": float(place.get("lon") or place.get("lng") or 0.0),
        "categories": categories,
        "website": place.get("website"),
        "phone": place.get("phone"),
    }


async def _search_and_build(location: str, kind: str, keyword: str = "") -> tuple[list[dict[str, Any]], bool]:
    place_type = {"hotel": "lodging", "restaurant": "restaurant", "attraction": "tourist_attraction"}[kind]
    limit = 5
    try:
        raw_places = await asyncio.wait_for(
            local_search_places(location=location, place_type=place_type, keyword=keyword, max_results=limit),
            timeout=2.5,
        )
    except Exception as exc:
        logger.warning("Local search failed for %s in %s: %s", kind, location, exc)
        raw_places = []

    raw_places = [
        place
        for place in raw_places
        if place.get("place_id")
    ]
    if not raw_places:
        logger.warning("[REC] WARNING: No %s found for %s. Returning empty recommendations.", kind + "s", location)
        return [], False

    limited_places = raw_places[:limit]
    enriched = await asyncio.gather(*[_enrich_place(location, place, kind) for place in limited_places])
    return enriched, False


def _flatten_location_recommendations(
    recommendation_blocks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    hotels: list[dict[str, Any]] = []
    restaurants: list[dict[str, Any]] = []
    attractions: list[dict[str, Any]] = []

    for block in recommendation_blocks:
        hotels.extend(block.get("hotels", []))
        restaurants.extend(block.get("restaurants", []))
        attractions.extend(block.get("attractions", []))

    return hotels, restaurants, attractions


def _make_pdf(
    state: TripState,
    hotels: list[dict[str, Any]],
    restaurants: list[dict[str, Any]],
    attractions: list[dict[str, Any]],
) -> str:
    # Keep generated reports inside the backend tree so download endpoints can resolve them consistently.
    report_dir = Path(settings.reports_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    def _slug(value: Any) -> str:
        text = "".join(char if str(char).isalnum() else "_" for char in str(value or "").strip())
        text = "_".join(part for part in text.split("_") if part)
        return text or "Trip"

    origin = _slug(state.get("origin", "Trip"))
    destination = _slug(state.get("destination", "Trip"))
    pdf_path = report_dir / f"RoadMind_{origin}_{destination}.pdf"

    mcp_generate_pdf_report(
        {
            "origin": state.get("origin", ""),
            "destination": state.get("destination", ""),
            "travel_dates": state.get("travel_dates", {}),
            "route": {
                "distance_km": state.get("route", {}).get("distance_km", state.get("route_distance_km", 0)),
                "duration_hours": state.get("route", {}).get("duration_hours", state.get("route_duration_hours", 0)),
                "toll_roads": state.get("toll_roads", False),
                "polyline": state.get("route", {}).get("polyline", state.get("polyline", [])),
                "coordinates": state.get("route", {}).get("coordinates", state.get("polyline", [])),
            },
            "weather": state.get("weather", []),
            "budget": {
                "fuel": state.get("fuel_cost_inr", 0),
                "tolls": state.get("toll_cost_inr", 0),
                "hotels": state.get("hotel_cost_inr", 0),
                "food": state.get("food_cost_inr", 0),
                "miscellaneous": state.get("miscellaneous_cost_inr", 0),
                "total_inr": state.get("total_inr", 0),
                "total_usd": state.get("total_usd", 0),
            },
            "vehicle": state.get("vehicle", {}),
            "fuel_calculation": state.get("fuel_calculation", {}),
            "trip_days": state.get("trip_days") or len(state.get("itinerary", {}).get("days", [])) or 1,
            "number_of_people": state.get("number_of_people", 1),
            "waypoints": state.get("waypoints", []),
            "report_summary": state.get("report_summary", ""),
            "itinerary": state.get("itinerary", {}),
            "recommendations": {
                "hotels": hotels,
                "restaurants": restaurants,
                "attractions": attractions,
            },
        },
        str(pdf_path),
    )
    return str(pdf_path)


async def recommendation_agent(state: TripState) -> TripState:
    origin = _normalize_location(state.get("origin"))
    requested_destination = _normalize_location(state.get("destination")) or _destination_from_user_input(state.get("user_input"))
    destination = requested_destination
    normalized_destination = normalize_place_name(destination)

    print("=== RECOMMENDATION AGENT ===")
    print(f"Origin received: '{origin}'")
    print(f"Destination received: '{destination}'")
    print(f"requested_origin = {origin}")
    print(f"requested_destination = {destination}")
    print(f"normalized_destination = {normalized_destination}")
    print(f"Will fetch recommendations for: '{destination}'")

    clear_cache()
    print("DEBUG: coordinates cache cleared")
    target_city = destination.strip()
    print(f"destination_used_for_osm = {target_city}")
    print(f"destination_used_for_llm = {target_city}")
    print(f"Target city for API calls: '{target_city}'")
    print(f"DEBUG: fetching recommendations for: {target_city}")

    seeded_catalog = state.get("recommendation_catalog")
    destination_catalog: dict[str, Any]
    if isinstance(seeded_catalog, dict) and any(
        isinstance(seeded_catalog.get(key), list) and seeded_catalog.get(key)
        for key in ("hotels", "restaurants", "attractions")
    ):
        destination_catalog = {
            "destination": _normalize_location(seeded_catalog.get("destination")) or target_city or destination,
            "hotels": list(seeded_catalog.get("hotels", [])),
            "restaurants": list(seeded_catalog.get("restaurants", [])),
            "attractions": list(seeded_catalog.get("attractions", [])),
            "fallback_generated": bool(seeded_catalog.get("fallback_generated", False)),
        }
        print("DEBUG: using pre-discovered destination catalog from trip state")
    else:
        destination_catalog = await build_destination_recommendations(target_city or destination)

    async def build_for_location(location: str) -> dict[str, Any]:
        hotels = validate_destination_places(location, list(destination_catalog.get("hotels", [])))
        restaurants = validate_destination_places(location, list(destination_catalog.get("restaurants", [])))
        attractions = validate_destination_places(location, list(destination_catalog.get("attractions", [])))
        print(f"OK: Destination: {location}")
        print(f"OK: Hotels found: {len(hotels)}")
        print(f"OK: Restaurants found: {len(restaurants)}")
        print(f"OK: Attractions found: {len(attractions)}")
        return {
            "location": location,
            "hotels": hotels,
            "restaurants": restaurants,
            "attractions": attractions,
            "no_results": {
                "hotels": not bool(hotels),
                "restaurants": not bool(restaurants),
                "attractions": not bool(attractions),
            },
        }

    recommendation_blocks = [await build_for_location(target_city or destination)]

    hotels, restaurants, attractions = _flatten_location_recommendations(recommendation_blocks)

    pdf_path = None
    try:
        pdf_path = _make_pdf(state, hotels, restaurants, attractions)
    except Exception as exc:
        state.setdefault("warnings", []).append(f"PDF report generation failed: {exc}")

    state["recommendations"] = recommendation_blocks
    state["recommendation_catalog"] = destination_catalog
    state["hotels"] = hotels
    state["restaurants"] = restaurants
    state["attractions"] = attractions
    state["osm_places"] = [
        place
        for place in [*hotels, *restaurants, *attractions]
        if isinstance(place, dict)
    ]
    state["rag_context"] = []
    state["pdf_path"] = pdf_path
    state["report_summary"] = (
        f"{target_city or destination} is a strong road trip match for {origin or 'your origin'} "
        f"with practical stops for hotels, food, and attractions."
    )
    if state.get("recommendations"):
        print(f"OK: Final hotel count: {len(state['recommendations'][0]['hotels'])}")
    state["trip_report"] = {
        "summary": state["report_summary"],
        "highlights": [
            f"Route length: {state.get('route_distance_km', 0)} km",
            f"Estimated budget: INR {state.get('total_inr', 0)}",
        ],
        "pdf_path": pdf_path,
        "rag_context": [],
        "recommendations": recommendation_blocks,
    }
    print(f"first_5_selected_places = {[item.get('name') for item in (hotels + restaurants + attractions)[:5]]}")

    return state
