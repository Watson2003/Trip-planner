from __future__ import annotations

import json
import logging
import re
from copy import deepcopy
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta
from contextvars import ContextVar
from typing import Any

from agents.state import TripState
from models.itinerary_schemas import ActivityCategory, DayItinerary, FullItinerary, TimeSlot
from utils.place_clustering import (
    cluster_places_by_distance,
    estimate_travel_time_minutes,
    haversine_distance_km,
    sort_places_nearest_neighbor,
)
from utils.destination_places import build_destination_attractions, build_destination_place_pools
from utils.llm import call_llm_json


logger = logging.getLogger(__name__)


def _normalize_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _place_lat_lon(place: dict[str, Any]) -> tuple[float | None, float | None]:
    lat = place.get("latitude")
    lon = place.get("longitude")
    if lat is None:
        lat = place.get("lat")
    if lon is None:
        lon = place.get("lng")
    if lon is None:
        lon = place.get("lon")
    try:
        if lat is None or lon is None:
            return None, None
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None, None


def _best_time_rank(value: Any) -> int:
    text = _normalize_text(value).casefold()
    if "morning" in text and "late" not in text:
        return 0
    if "late morning" in text:
        return 1
    if "afternoon" in text:
        return 2
    if "evening" in text:
        return 3
    return 4


def _estimate_travel_time_minutes(distance_km: float) -> int:
    if distance_km <= 0:
        return 0
    # Hill-station sightseeing is usually slower than highway driving.
    minutes = int(round((distance_km / 18.0) * 60))
    return max(6, min(45, minutes))


def _slot_lat_lon(slot: TimeSlot) -> tuple[float | None, float | None]:
    try:
        lat = getattr(slot, "latitude", None)
        lon = getattr(slot, "longitude", None)
    except Exception:
        return None, None
    try:
        if lat is None or lon is None:
            return None, None
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None, None


def _slot_reference_name(slot: TimeSlot) -> str:
    for raw in (slot.place_name, slot.location, slot.title, slot.activity):
        label = _normalize_text(raw)
        if not label:
            continue
        normalized = normalize_place_name(label)
        if normalized:
            return label
    return _normalize_text(slot.location)


def _apply_location_flow(
    day_slots: list[TimeSlot],
    *,
    start_location: str,
    day_kind: str = "",
    destination: str = "",
) -> list[TimeSlot]:
    adjusted: list[TimeSlot] = []
    previous_name = _normalize_text(start_location)
    previous_lat_lon: tuple[float | None, float | None] = (None, None)

    for slot in day_slots:
        slot_name = _slot_reference_name(slot)
        slot_lat_lon = _slot_lat_lon(slot)
        before_name = previous_name or _normalize_text(slot.current_location_before) or _normalize_text(slot.location)
        if slot.type == ActivityCategory.DRIVE:
            after_name = _normalize_text(slot.current_location_after) or _normalize_text(slot.location) or slot_name or before_name
        else:
            after_name = slot_name or _normalize_text(slot.current_location_after) or _normalize_text(slot.location) or before_name
            if day_kind == "arrival" and slot.type == ActivityCategory.LUNCH and destination:
                after_name = destination

        travel_time_minutes: int | None = slot.travel_time_minutes
        if slot.type == ActivityCategory.DRIVE:
            travel_time_minutes = max(travel_time_minutes or 0, slot.estimated_duration_minutes)
        else:
            prev_norm = normalize_place_name(before_name)
            after_norm = normalize_place_name(after_name)
            if prev_norm and after_norm and prev_norm == after_norm:
                travel_time_minutes = 0
            elif previous_lat_lon[0] is not None and previous_lat_lon[1] is not None and slot_lat_lon[0] is not None and slot_lat_lon[1] is not None:
                distance = haversine_distance_km(previous_lat_lon[0], previous_lat_lon[1], slot_lat_lon[0], slot_lat_lon[1])
                travel_time_minutes = _estimate_travel_time_minutes(distance)
            elif travel_time_minutes is None:
                travel_time_minutes = 0 if prev_norm and after_norm and prev_norm == after_norm else 8

        adjusted.append(
            slot.model_copy(
                update={
                    "current_location_before": before_name,
                    "current_location_after": after_name,
                    "travel_time_minutes": travel_time_minutes,
                }
            )
        )

        previous_name = after_name
        if slot_lat_lon[0] is not None and slot_lat_lon[1] is not None:
            previous_lat_lon = slot_lat_lon

    return adjusted


def normalize_place_name(name: str) -> str:
    """Normalize a place label for duplicate detection."""
    text = _normalize_text(name).casefold()
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
        "final stop at ",
        "fuel and tea stop at ",
        "fuel and tea break at ",
        "fuel stop at ",
        "check in at ",
        "check-in at ",
        "stay at ",
        "lunch at ",
        "dinner at ",
        "breakfast at ",
        "breakfast near ",
        "lunch near ",
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
        "drive from ",
        "drive back to ",
        "return to ",
        "arrive back at ",
        "at ",
        "hotel ",
        "restaurant ",
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

    stripped = re.sub(r"\s+", " ", stripped).strip()
    return stripped


def is_duplicate_place(name: str, used_places: set[str]) -> bool:
    normalized = normalize_place_name(name)
    return bool(normalized and normalized in used_places)


def _reserve_place(name: str, used_places: set[str]) -> str:
    normalized = normalize_place_name(name)
    if normalized:
        used_places.add(normalized)
    return normalized


def _clean_place_entry(item: dict[str, Any], fallback_name: str, fallback_description: str = "") -> dict[str, Any]:
    entry = dict(item)
    entry["name"] = _normalize_text(entry.get("name"), fallback_name)
    entry["description"] = _normalize_text(entry.get("description"), fallback_description)
    return entry


def _unique_place_entries(entries: list[dict[str, Any]], used: set[str]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    for entry in entries:
        name = _normalize_text(entry.get("name"))
        normalized = normalize_place_name(name)
        if not normalized or normalized in used:
            continue
        used.add(normalized)
        unique.append(dict(entry, name=name))
    return unique


def _destination_key(destination: str) -> str:
    return normalize_place_name(destination)


def _fallback_place_entry(destination: str, category: str, index: int) -> dict[str, Any]:
    base = _normalize_text(destination, "Destination")
    if category == "hotels":
        hotel_names = [
            f"{base} Central Stay",
            f"{base} Comfort Hotel",
            f"{base} Grand Residency",
            f"{base} Heritage Suites",
        ]
        name = hotel_names[index % len(hotel_names)]
        return {
            "name": name,
            "description": f"Reliable stay option in or near {base}.",
            "category": "hotel",
        }
    if category == "restaurants":
        restaurant_names = [
            f"{base} Spice House",
            f"{base} Family Dining",
            f"{base} Tea & Tiffin",
            f"{base} Highway Kitchen",
            f"{base} Kitchen",
        ]
        name = restaurant_names[index % len(restaurant_names)]
        return {
            "name": name,
            "description": f"Practical meal stop for travelers visiting {base}.",
            "category": "restaurant",
        }
    if category == "fuel_stops":
        fuel_names = [
            f"{base} Fuel Stop",
            f"{base} Bypass Fuel Point",
            f"{base} Highway Fuel Hub",
        ]
        name = fuel_names[index % len(fuel_names)]
        return {
            "name": name,
            "description": f"Fuel and quick refreshment stop near {base}.",
            "category": "fuel_stop",
        }
    if category == "rest_stops":
        rest_names = [
            f"{base} Tea Stop",
            f"{base} Rest Point",
            f"{base} Highway Halt",
        ]
        name = rest_names[index % len(rest_names)]
        return {
            "name": name,
            "description": f"Short rest stop for a road trip around {base}.",
            "category": "rest_stop",
        }

    attraction_names = [
        f"{base} Botanical Garden",
        f"{base} Lake View",
        f"{base} Heritage Museum",
        f"{base} Scenic Point",
        f"{base} Cultural Walk",
    ]
    name = attraction_names[index % len(attraction_names)]
    return {
        "name": name,
        "description": f"Local sightseeing stop around {base}.",
        "category": "attraction",
    }


OOTY_PLACE_POOL: dict[str, list[dict[str, Any]]] = {
    "attractions": [
        {"name": "Ooty Botanical Garden", "description": "A classic botanical garden with seasonal blooms and shaded paths.", "category": "attraction"},
        {"name": "Ooty Lake", "description": "A scenic lake for relaxed sightseeing and boat rides.", "category": "attraction"},
        {"name": "Doddabetta Peak", "description": "The highest peak in the Nilgiris with sweeping hill views.", "category": "attraction"},
        {"name": "Rose Garden", "description": "A colorful hillside garden known for its rose varieties.", "category": "attraction"},
        {"name": "Thread Garden", "description": "An unusual hand-crafted garden attraction in Ooty.", "category": "attraction"},
        {"name": "Pykara Lake", "description": "A calm lake stop ideal for a half-day scenic outing.", "category": "attraction"},
        {"name": "Tea Museum", "description": "A tea heritage stop with local processing stories and tastings.", "category": "attraction"},
        {"name": "Avalanche Lake", "description": "A quieter lake destination with a more natural setting.", "category": "attraction"},
        {"name": "Emerald Lake", "description": "A peaceful reservoir-style stop with hill scenery.", "category": "attraction"},
        {"name": "Nilgiri Mountain Railway", "description": "A heritage rail experience that is iconic to the region.", "category": "attraction"},
        {"name": "Government Museum", "description": "A cultural stop for local history and artifacts.", "category": "attraction"},
        {"name": "St Stephen’s Church", "description": "A historic church and a quiet architectural stop.", "category": "attraction"},
    ],
    "restaurants": [
        {"name": "Earl’s Secret", "description": "A well-known dining spot with a relaxed Ooty atmosphere.", "category": "restaurant"},
        {"name": "Place To Bee", "description": "A cozy cafe-style restaurant for breakfast or lunch.", "category": "restaurant"},
        {"name": "Nahar Restaurant", "description": "A dependable multi-cuisine restaurant in town.", "category": "restaurant"},
        {"name": "Hyderabad Biryani House Ooty", "description": "A hearty biryani stop for lunch or dinner.", "category": "restaurant"},
        {"name": "Junior Kuppanna", "description": "A popular South Indian and non-veg dining option.", "category": "restaurant"},
        {"name": "Shinkows", "description": "A classic multi-cuisine restaurant for a comfortable meal.", "category": "restaurant"},
        {"name": "Ooty Coffee House", "description": "A simple coffee-and-tiffin stop for travelers.", "category": "restaurant"},
        {"name": "Ascot Multi Cuisine Restaurant", "description": "A sit-down dinner option near the hill town center.", "category": "restaurant"},
    ],
    "hotels": [
        {"name": "Hotel Lakeview", "description": "A practical stay with views and easy access to Ooty attractions.", "category": "hotel"},
        {"name": "Sterling Ooty Elk Hill", "description": "A popular resort-style stay on the hills.", "category": "hotel"},
        {"name": "Sinclairs Retreat Ooty", "description": "A calm retreat for travelers wanting a comfortable base.", "category": "hotel"},
        {"name": "Gem Park Ooty", "description": "A well-known hotel option with dependable service.", "category": "hotel"},
        {"name": "Savoy Ooty", "description": "A heritage-style stay with classic hill-station charm.", "category": "hotel"},
        {"name": "Meadows Residency", "description": "A straightforward stay with good access to the town.", "category": "hotel"},
        {"name": "Accord Highland Ooty", "description": "A premium stay suitable for a family road trip.", "category": "hotel"},
    ],
    "fuel_stops": [
        {"name": "Coimbatore Bypass Fuel Stop", "description": "A convenient fuel stop before entering the hill route.", "category": "fuel_stop"},
        {"name": "Mettupalayam Highway Fuel Point", "description": "A practical fuel stop on the approach to Ooty.", "category": "fuel_stop"},
        {"name": "Nilgiri Roadside Fuel Stop", "description": "A quick top-up point before hill driving.", "category": "fuel_stop"},
        {"name": "Kothagiri Fuel & Tea Stop", "description": "A fuel stop paired with a quick tea break.", "category": "fuel_stop"},
        {"name": "Ooty Bypass Fuel Hub", "description": "A roadside fuel and convenience stop near the destination.", "category": "fuel_stop"},
    ],
    "rest_stops": [
        {"name": "Mettupalayam Tea Stop", "description": "A short refreshment stop on the route to Ooty.", "category": "rest_stop"},
        {"name": "Coonoor View Point Stop", "description": "A scenic break point before the final hill stretch.", "category": "rest_stop"},
        {"name": "Nilgiri Highway Rest Stop", "description": "A simple rest stop with room to stretch and recover.", "category": "rest_stop"},
        {"name": "Coimbatore Bypass Rest Stop", "description": "A practical break stop before the climb into the hills.", "category": "rest_stop"},
    ],
}

_ACTIVE_PLACE_POOLS: ContextVar[dict[str, dict[str, list[dict[str, Any]]]]] = ContextVar(
    "_ACTIVE_PLACE_POOLS",
    default={},
)


def _set_active_place_pools(pools: dict[str, dict[str, list[dict[str, Any]]]]):
    return _ACTIVE_PLACE_POOLS.set(pools)


def _reset_active_place_pools(token) -> None:
    _ACTIVE_PLACE_POOLS.reset(token)


def _current_active_place_pools() -> dict[str, dict[str, list[dict[str, Any]]]]:
    return _ACTIVE_PLACE_POOLS.get()


def _coerce_place_pool_entries(
    items: Any,
    *,
    destination: str,
    category: str,
    limit: int,
) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []

    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        if isinstance(item, str):
            entry = _fallback_place_entry(destination, category, index)
            entry["name"] = item
        elif isinstance(item, dict):
            entry = _clean_place_entry(item, _fallback_place_entry(destination, category, index)["name"])
        else:
            continue

        normalized = normalize_place_name(entry.get("name", ""))
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(entry)
        if len(cleaned) >= limit:
            break
    return cleaned


def _merge_place_candidates(
    destination: str,
    category: str,
    primary: list[dict[str, Any]],
    secondary: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, entry in enumerate(primary + secondary):
        name = _normalize_text(entry.get("name"), _fallback_place_entry(destination, category, index).get("name", ""))
        normalized = normalize_place_name(name)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(_clean_place_entry(entry, name))
        if len(merged) >= limit:
            break
    return merged


def _generate_dynamic_destination_pool(destination: str) -> dict[str, list[dict[str, Any]]]:
    return build_destination_place_pools(destination, include_llm=True)


def _build_destination_place_pool(
    destination: str,
    *,
    recommendations: dict[str, Any] | None = None,
    allow_llm: bool = True,
) -> dict[str, list[dict[str, Any]]]:
    recs = recommendations or {}
    recommendation_pool = {
        "attractions": _coerce_place_pool_entries(recs.get("attractions"), destination=destination, category="attractions", limit=8),
        "restaurants": _coerce_place_pool_entries(recs.get("restaurants"), destination=destination, category="restaurants", limit=8),
        "hotels": _coerce_place_pool_entries(recs.get("hotels"), destination=destination, category="hotels", limit=5),
        "fuel_stops": _coerce_place_pool_entries(recs.get("fuel_stops"), destination=destination, category="fuel_stops", limit=5),
        "rest_stops": _coerce_place_pool_entries(recs.get("rest_stops"), destination=destination, category="rest_stops", limit=5),
    }

    if not any(recommendation_pool.values()) and not allow_llm:
        return {
            "hotels": [_fallback_place_entry(destination, "hotels", index) for index in range(5)],
            "restaurants": [_fallback_place_entry(destination, "restaurants", index) for index in range(8)],
            "attractions": [_fallback_place_entry(destination, "attractions", index) for index in range(8)],
            "fuel_stops": [_fallback_place_entry(destination, "fuel_stops", index) for index in range(5)],
            "rest_stops": [_fallback_place_entry(destination, "rest_stops", index) for index in range(5)],
        }

    base_pool = (
        {
            "attractions": [],
            "restaurants": [],
            "hotels": [],
            "fuel_stops": [],
            "rest_stops": [],
        }
        if any(recommendation_pool.values())
        else build_destination_place_pools(destination, include_llm=allow_llm)
    )

    final_pool: dict[str, list[dict[str, Any]]] = {}
    for category, target_count in (
        ("hotels", 5),
        ("restaurants", 8),
        ("attractions", 8),
        ("fuel_stops", 5),
        ("rest_stops", 5),
    ):
        final_pool[category] = _merge_place_candidates(
            destination,
            category,
            recommendation_pool.get(category, []),
            base_pool.get(category, []),
            limit=target_count,
        )
        if not final_pool[category]:
            final_pool[category] = [
                _fallback_place_entry(destination, category, index)
                for index in range(target_count)
            ]
            final_pool[category] = _unique_place_entries(final_pool[category], set())
    return final_pool


def get_unique_place(category: str, destination: str, used_places: set[str]) -> dict[str, Any]:
    category_key = _normalize_text(category).casefold().replace(" ", "_")
    location_key = _destination_key(destination)
    active_pools = dict(_current_active_place_pools())
    pools = active_pools.get(location_key)
    if pools is None:
        pools = _build_destination_place_pool(destination)
        active_pools[location_key] = pools
        _set_active_place_pools(active_pools)

    candidates = list(pools.get(category_key, []))
    if not candidates and category_key in {"hotel", "restaurant", "attraction", "fuel_stop", "rest_stop"}:
        plural_map = {
            "hotel": "hotels",
            "restaurant": "restaurants",
            "attraction": "attractions",
            "fuel_stop": "fuel_stops",
            "rest_stop": "rest_stops",
        }
        candidates = list(pools.get(plural_map[category_key], []))

    for candidate in candidates:
        name = _normalize_text(candidate.get("name"))
        if name and not is_duplicate_place(name, used_places):
            _reserve_place(name, used_places)
            return dict(candidate, name=name)

    fallback = _fallback_place_entry(destination, category_key, len(used_places))
    name = _normalize_text(fallback.get("name"))
    suffix = 2
    candidate_name = name
    while is_duplicate_place(candidate_name, used_places):
        candidate_name = f"{name} {suffix}"
        suffix += 1
    fallback["name"] = candidate_name
    _reserve_place(candidate_name, used_places)
    return fallback


def _slot_category_pool(slot_type: ActivityCategory) -> str | None:
    if slot_type in {ActivityCategory.BREAKFAST, ActivityCategory.LUNCH, ActivityCategory.DINNER}:
        return "restaurants"
    if slot_type in {ActivityCategory.ATTRACTION, ActivityCategory.SIGHTSEEING}:
        return "attractions"
    if slot_type == ActivityCategory.FUEL:
        return "fuel_stops"
    return None


def _slot_place_label(slot: TimeSlot) -> str:
    for raw in (slot.title, slot.activity, slot.location):
        label = _normalize_text(raw)
        if not label:
            continue
        normalized = normalize_place_name(label)
        if normalized:
            return normalized
    return ""


def _replace_slot_place_text(text: str, replacement: str) -> str:
    raw = _normalize_text(text)
    if not raw:
        return replacement

    lower = raw.casefold()
    for separator in (" at ", " near ", " to "):
        if separator in lower:
            prefix = raw.rsplit(separator, 1)[0].strip()
            if prefix:
                return f"{prefix}{separator}{replacement}"

    parts = raw.split(maxsplit=1)
    if len(parts) == 2:
        return f"{parts[0]} {replacement}"
    return replacement


def _validate_unique_itinerary_places(days: list[DayItinerary]) -> list[DayItinerary]:
    seen: set[str] = set()
    for day in days:
        filtered_slots: list[TimeSlot] = []
        rest_count = 0
        for slot in day.time_slots:
            if slot.type == ActivityCategory.REST:
                if rest_count >= 1:
                    continue
                rest_count += 1

            slot_label = _slot_place_label(slot)
            if not slot_label or slot_label not in seen:
                if slot_label:
                    seen.add(slot_label)
                filtered_slots.append(slot)
                continue

            replacement_category = _slot_category_pool(slot.type)
            if not replacement_category:
                continue

            replacement_location = slot.location
            if slot.type in {ActivityCategory.BREAKFAST, ActivityCategory.LUNCH, ActivityCategory.DINNER, ActivityCategory.ATTRACTION, ActivityCategory.SIGHTSEEING, ActivityCategory.HOTEL}:
                replacement_location = replacement_location or slot.current_location_after or slot.current_location_before
            replacement = get_unique_place(replacement_category, replacement_location or slot.location or "", seen)
            replacement_name = _normalize_text(replacement.get("name"), replacement_location or slot.location or "")
            if not replacement_name:
                continue

            slot.title = _replace_slot_place_text(slot.title, replacement_name)
            slot.activity = _replace_slot_place_text(slot.activity or slot.title, replacement_name)
            if slot.type != ActivityCategory.DRIVE:
                slot.location = _normalize_text(replacement.get("address"), slot.location)
            seen.add(normalize_place_name(replacement_name))
            filtered_slots.append(slot)

        target_attraction_cap = 5
        if day.day_number == 1 and len(days) > 1:
            target_attraction_cap = 2
        elif day.day_number == len(days) and len(days) >= 3:
            target_attraction_cap = 3

        attraction_indices = [
            index
            for index, slot in enumerate(filtered_slots)
            if slot.type in {ActivityCategory.ATTRACTION, ActivityCategory.SIGHTSEEING}
        ]
        if len(attraction_indices) > target_attraction_cap:
            for index in reversed(attraction_indices[target_attraction_cap:]):
                filtered_slots.pop(index)

        day.time_slots = filtered_slots
    return days


def _itinerary_place_names(days: list[DayItinerary]) -> list[str]:
    names: list[str] = []
    for day in days:
        for slot in day.time_slots:
            if slot.type not in {
                ActivityCategory.BREAKFAST,
                ActivityCategory.LUNCH,
                ActivityCategory.DINNER,
                ActivityCategory.ATTRACTION,
                ActivityCategory.SIGHTSEEING,
                ActivityCategory.HOTEL,
                ActivityCategory.FUEL,
            }:
                continue
            label = _normalize_text(slot.place_name or slot.title or slot.activity or "")
            normalized = normalize_place_name(label)
            if normalized:
                names.append(normalized)
    return names



def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _as_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, Mapping):
        return [dict(value)]
    return []


def _parse_start_date(dates: Any) -> datetime:
    date_text = _normalize_text(dates)
    if " to " in date_text:
        date_text = date_text.split(" to ", 1)[0].strip()

    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(date_text, fmt)
        except ValueError:
            continue
    return datetime.now()


def _strip_code_fences(text: str) -> str:
    clean = text.strip()
    if "```" not in clean:
        return clean

    parts = clean.split("```")
    for part in parts:
        candidate = part.strip()
        if candidate.startswith("json"):
            candidate = candidate[4:].strip()
        if candidate.startswith("{") and candidate.endswith("}"):
            return candidate
    for part in parts:
        candidate = part.strip()
        if "{" in candidate and "}" in candidate:
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start != -1 and end != -1 and end > start:
                return candidate[start : end + 1]
    return clean


def _category_from_value(value: Any) -> ActivityCategory:
    if isinstance(value, ActivityCategory):
        return value
    raw_value = getattr(value, "value", value)
    try:
        return ActivityCategory(str(raw_value).strip().lower())
    except Exception:
        return ActivityCategory.MISC


def _slot(
    *,
    time: str,
    activity: str,
    location: str,
    description: str,
    duration_minutes: int,
    category: ActivityCategory,
    estimated_cost_inr: float,
    tips: str = "",
    place_name: str = "",
    best_time_to_visit: str = "",
    nearby_places: list[str] | None = None,
) -> TimeSlot:
    return TimeSlot(
        time=time,
        activity=activity,
        location=location,
        description=description,
        duration_minutes=max(5, duration_minutes),
        category=category,
        estimated_cost_inr=max(0.0, round(estimated_cost_inr, 2)),
        tips=tips,
        place_name=place_name,
        best_time_to_visit=best_time_to_visit,
        nearby_places=nearby_places or [],
    )


def _fuel_estimate(distance_km: float, vehicle_type: str) -> float:
    fuel_efficiency_kmpl = {
        "car": 18.0,
        "suv": 14.0,
        "sedan": 17.0,
        "hatchback": 20.0,
        "scooter": 45.0,
        "bike": 35.0,
    }.get(vehicle_type.lower(), 18.0)
    fuel_price_per_litre = 105.0
    litres_needed = max(1.0, distance_km / max(1.0, fuel_efficiency_kmpl))
    return round(litres_needed * fuel_price_per_litre, 2)


def _fallback_slot_cost(
    category: ActivityCategory,
    *,
    distance_km: float,
    vehicle_type: str,
    is_travel_day: bool,
    is_return_day: bool,
) -> float:
    if category in (ActivityCategory.DRIVE, ActivityCategory.REST):
        return 0.0
    if category == ActivityCategory.BREAKFAST:
        return 160.0 if is_travel_day else 180.0
    if category == ActivityCategory.LUNCH:
        return 280.0 if is_travel_day else 350.0
    if category == ActivityCategory.DINNER:
        return 380.0 if is_return_day else 450.0
    if category == ActivityCategory.FUEL:
        return max(250.0, min(2500.0, _fuel_estimate(distance_km, vehicle_type)))
    if category == ActivityCategory.HOTEL:
        return 1800.0 if is_travel_day else 2200.0
    if category in (ActivityCategory.SIGHTSEEING, ActivityCategory.ATTRACTION):
        return 50.0
    if category == ActivityCategory.SHOPPING:
        return 500.0
    return 100.0


def _normalize_slot_cost(
    cost: float,
    category: ActivityCategory,
    *,
    distance_km: float,
    vehicle_type: str,
    is_travel_day: bool,
    is_return_day: bool,
) -> float:
    if not cost or cost < 0:
        return _fallback_slot_cost(
            category,
            distance_km=distance_km,
            vehicle_type=vehicle_type,
            is_travel_day=is_travel_day,
            is_return_day=is_return_day,
        )

    caps = {
        ActivityCategory.BREAKFAST: 800.0,
        ActivityCategory.LUNCH: 1200.0,
        ActivityCategory.DINNER: 1500.0,
        ActivityCategory.HOTEL: 10000.0,
        ActivityCategory.FUEL: 5000.0,
        ActivityCategory.SIGHTSEEING: 1000.0,
        ActivityCategory.ATTRACTION: 1000.0,
        ActivityCategory.SHOPPING: 10000.0,
        ActivityCategory.DRIVE: 0.0,
        ActivityCategory.REST: 0.0,
    }
    cap = caps.get(category, 2000.0)
    if cap == 0.0:
        return 0.0

    normalized = min(cost, cap)
    floor = _fallback_slot_cost(
        category,
        distance_km=distance_km,
        vehicle_type=vehicle_type,
        is_travel_day=is_travel_day,
        is_return_day=is_return_day,
    )
    return max(floor, normalized)


def _hotel_name(hotels: list[dict[str, Any]], destination: str, index: int = 0) -> str:
    if hotels and hotels[index % len(hotels)].get("name"):
        return str(hotels[index % len(hotels)]["name"])
    return f"{destination} Stay"


def _restaurant_name(restaurants: list[dict[str, Any]], destination: str, index: int = 0) -> str:
    if restaurants and restaurants[index % len(restaurants)].get("name"):
        return str(restaurants[index % len(restaurants)]["name"])
    return f"{destination} Dining"


def _attraction_name(attractions: list[dict[str, Any]], destination: str, index: int = 0) -> str:
    if attractions and attractions[index % len(attractions)].get("name"):
        return str(attractions[index % len(attractions)]["name"])
    return f"{destination} Sightseeing Spot"


def _build_fallback_itinerary(
    *,
    state: TripState,
    origin: str,
    destination: str,
    start_date: datetime,
    trip_days: int,
    budget: float,
    vehicle_type: str,
    distance_km: float,
    duration_hours: float,
    hotels: list[dict[str, Any]],
    restaurants: list[dict[str, Any]],
    attractions: list[dict[str, Any]],
) -> FullItinerary:
    generated_days: list[DayItinerary] = []
    total_cost = 0.0
    travel_tips = [
        "Start early to avoid city traffic and maximize sightseeing time.",
        "Keep cash and UPI both ready for small highway stops.",
        "Keep one flexible meal window for delays or weather changes.",
        "Carry water, light snacks, and a phone charger in the car.",
        "Check hotel check-in and check-out times a day before travel.",
    ]

    for day_index in range(trip_days):
        current_date = start_date + timedelta(days=day_index)
        day_number = day_index + 1
        is_travel_day = day_number == 1
        is_return_day = trip_days >= 3 and day_number == trip_days
        hotel_name = _hotel_name(hotels, destination, day_index)
        breakfast_place = _restaurant_name(restaurants, origin if is_travel_day else destination, day_index)
        lunch_place = _restaurant_name(restaurants, destination, day_index + 1)
        dinner_place = _restaurant_name(restaurants, destination, day_index + 2)
        attraction_one = _attraction_name(attractions, destination, day_index)
        attraction_two = _attraction_name(attractions, destination, day_index + 1)

        if is_travel_day:
            slots = [
                _slot(
                    time="06:30 AM",
                    activity=f"Breakfast at {breakfast_place}",
                    location=origin,
                    description="Have a light breakfast before starting the journey.",
                    duration_minutes=30,
                    category=ActivityCategory.BREAKFAST,
                    estimated_cost_inr=_fallback_slot_cost(
                        ActivityCategory.BREAKFAST,
                        distance_km=distance_km,
                        vehicle_type=vehicle_type,
                        is_travel_day=True,
                        is_return_day=False,
                    ),
                    tips="Keep the first leg light so the drive stays comfortable.",
                ),
                _slot(
                    time="07:15 AM",
                    activity=f"Depart for {destination}",
                    location=f"{origin} to {destination}",
                    description=f"Begin the drive towards {destination} with planned breaks.",
                    duration_minutes=max(60, int(duration_hours * 60 * 0.45)),
                    category=ActivityCategory.DRIVE,
                    estimated_cost_inr=0,
                    tips="Leave early to avoid traffic and road delays.",
                ),
                _slot(
                    time="11:00 AM",
                    activity="Fuel and refreshment stop",
                    location="Highway stop",
                    description="Stretch, refuel if needed, and take a short break from driving.",
                    duration_minutes=25,
                    category=ActivityCategory.FUEL,
                    estimated_cost_inr=_fallback_slot_cost(
                        ActivityCategory.FUEL,
                        distance_km=distance_km,
                        vehicle_type=vehicle_type,
                        is_travel_day=True,
                        is_return_day=False,
                    ),
                    tips="Top up fuel before entering hill roads if applicable.",
                ),
                _slot(
                    time="01:30 PM",
                    activity=f"Lunch at {lunch_place}",
                    location=destination,
                    description="Enjoy a proper lunch after the long drive.",
                    duration_minutes=45,
                    category=ActivityCategory.LUNCH,
                    estimated_cost_inr=_fallback_slot_cost(
                        ActivityCategory.LUNCH,
                        distance_km=distance_km,
                        vehicle_type=vehicle_type,
                        is_travel_day=True,
                        is_return_day=False,
                    ),
                    tips="Choose a place close to your hotel to reduce extra travel.",
                ),
                _slot(
                    time="03:00 PM",
                    activity=f"Check in at {hotel_name}",
                    location=destination,
                    description="Arrive at the hotel, check in, and unpack for the stay.",
                    duration_minutes=40,
                    category=ActivityCategory.HOTEL,
                    estimated_cost_inr=_fallback_slot_cost(
                        ActivityCategory.HOTEL,
                        distance_km=distance_km,
                        vehicle_type=vehicle_type,
                        is_travel_day=True,
                        is_return_day=False,
                    ),
                    tips="Confirm parking, breakfast timings, and Wi-Fi during check-in.",
                ),
                _slot(
                    time="05:30 PM",
                    activity="Short rest and freshen up",
                    location=hotel_name,
                    description="Rest after travel and prepare for evening exploration.",
                    duration_minutes=60,
                    category=ActivityCategory.REST,
                    estimated_cost_inr=0,
                    tips="Use this pause to plan the next day and charge devices.",
                ),
                _slot(
                    time="08:00 PM",
                    activity=f"Dinner at {dinner_place}",
                    location=destination,
                    description="End the day with a relaxed local dinner near the hotel.",
                    duration_minutes=60,
                    category=ActivityCategory.DINNER,
                    estimated_cost_inr=_fallback_slot_cost(
                        ActivityCategory.DINNER,
                        distance_km=distance_km,
                        vehicle_type=vehicle_type,
                        is_travel_day=True,
                        is_return_day=False,
                    ),
                    tips="Keep dinner light if the next day starts early.",
                ),
            ]
            day_title = f"Departure Day - {origin} to {destination}"
            summary = f"Travel from {origin} to {destination}, check in, and settle into the trip."
            highlights = [
                f"Scenic drive from {origin} to {destination}",
                f"Relaxed hotel check-in at {hotel_name}",
                f"Evening dinner near the destination",
            ]
        elif is_return_day:
            slots = [
                _slot(
                    time="08:00 AM",
                    activity=f"Breakfast at {breakfast_place}",
                    location=destination,
                    description="Start the day with breakfast before the return or final sightseeing.",
                    duration_minutes=40,
                    category=ActivityCategory.BREAKFAST,
                    estimated_cost_inr=_fallback_slot_cost(
                        ActivityCategory.BREAKFAST,
                        distance_km=distance_km,
                        vehicle_type=vehicle_type,
                        is_travel_day=False,
                        is_return_day=True,
                    ),
                    tips="Keep checkout papers and bags ready before heading out.",
                ),
                _slot(
                    time="09:30 AM",
                    activity="Final sightseeing or checkout",
                    location=destination,
                    description="Use the morning for one last local stop or hotel checkout.",
                    duration_minutes=90,
                    category=ActivityCategory.SIGHTSEEING,
                    estimated_cost_inr=_fallback_slot_cost(
                        ActivityCategory.SIGHTSEEING,
                        distance_km=distance_km,
                        vehicle_type=vehicle_type,
                        is_travel_day=False,
                        is_return_day=True,
                    ),
                    tips="Pick a nearby attraction so you can leave on time.",
                ),
                _slot(
                    time="11:30 AM",
                    activity=f"Drive back to {origin}",
                    location=f"{destination} to {origin}",
                    description="Begin the return journey with a planned break schedule.",
                    duration_minutes=max(60, int(duration_hours * 60 * 0.55)),
                    category=ActivityCategory.DRIVE,
                    estimated_cost_inr=0,
                    tips="Take photos only during safe stopovers, not while driving.",
                ),
                _slot(
                    time="02:00 PM",
                    activity=f"Lunch at {lunch_place}",
                    location="Roadside stop",
                    description="Pause for lunch and a quick stretch during the return drive.",
                    duration_minutes=45,
                    category=ActivityCategory.LUNCH,
                    estimated_cost_inr=_fallback_slot_cost(
                        ActivityCategory.LUNCH,
                        distance_km=distance_km,
                        vehicle_type=vehicle_type,
                        is_travel_day=False,
                        is_return_day=True,
                    ),
                    tips="A quick, clean highway restaurant works best here.",
                ),
                _slot(
                    time="04:30 PM",
                    activity="Tea break and fuel check",
                    location="Highway stop",
                    description="Take a short tea break and top up fuel before the final stretch.",
                    duration_minutes=25,
                    category=ActivityCategory.FUEL,
                    estimated_cost_inr=_fallback_slot_cost(
                        ActivityCategory.FUEL,
                        distance_km=distance_km,
                        vehicle_type=vehicle_type,
                        is_travel_day=False,
                        is_return_day=True,
                    ),
                    tips="Refuel before the last 60-90 minutes of driving.",
                ),
                _slot(
                    time="07:30 PM",
                    activity="Arrive back home",
                    location=origin,
                    description="Reach home and wrap up the trip for the day.",
                    duration_minutes=30,
                    category=ActivityCategory.REST,
                    estimated_cost_inr=0,
                    tips="Unpack essentials first and rest after the drive.",
                ),
            ]
            day_title = f"Return Day - {destination} to {origin}"
            summary = f"Enjoy a final morning stop and return safely to {origin}."
            highlights = [
                "Final destination stop",
                f"Return drive from {destination} to {origin}",
                "End-of-trip fuel and tea break",
            ]
        else:
            slots = [
                _slot(
                    time="08:00 AM",
                    activity=f"Breakfast at {breakfast_place}",
                    location=destination,
                    description="Begin the day with a relaxed breakfast at a local spot.",
                    duration_minutes=40,
                    category=ActivityCategory.BREAKFAST,
                    estimated_cost_inr=_fallback_slot_cost(
                        ActivityCategory.BREAKFAST,
                        distance_km=distance_km,
                        vehicle_type=vehicle_type,
                        is_travel_day=False,
                        is_return_day=False,
                    ),
                    tips="Start with an early breakfast to maximize sightseeing.",
                ),
                _slot(
                    time="09:30 AM",
                    activity=f"Visit {attraction_one}",
                    location=destination,
                    description="Spend the morning exploring a major attraction.",
                    duration_minutes=120,
                    category=ActivityCategory.SIGHTSEEING,
                    estimated_cost_inr=_fallback_slot_cost(
                        ActivityCategory.SIGHTSEEING,
                        distance_km=distance_km,
                        vehicle_type=vehicle_type,
                        is_travel_day=False,
                        is_return_day=False,
                    ),
                    tips="Carry water and keep some cash for entry or parking.",
                ),
                _slot(
                    time="12:30 PM",
                    activity=f"Lunch at {lunch_place}",
                    location=destination,
                    description="Stop for lunch before continuing the sightseeing route.",
                    duration_minutes=60,
                    category=ActivityCategory.LUNCH,
                    estimated_cost_inr=_fallback_slot_cost(
                        ActivityCategory.LUNCH,
                        distance_km=distance_km,
                        vehicle_type=vehicle_type,
                        is_travel_day=False,
                        is_return_day=False,
                    ),
                    tips="Choose a restaurant close to the next attraction.",
                ),
                _slot(
                    time="02:00 PM",
                    activity=f"Explore {attraction_two}",
                    location=destination,
                    description="Continue the afternoon with a second scenic or cultural stop.",
                    duration_minutes=120,
                    category=ActivityCategory.SIGHTSEEING,
                    estimated_cost_inr=_fallback_slot_cost(
                        ActivityCategory.SIGHTSEEING,
                        distance_km=distance_km,
                        vehicle_type=vehicle_type,
                        is_travel_day=False,
                        is_return_day=False,
                    ),
                    tips="Keep the afternoon pace light if you are traveling with family.",
                ),
                _slot(
                    time="04:45 PM",
                    activity="Shopping / local market time",
                    location=destination,
                    description="Pick up souvenirs, snacks, or local products.",
                    duration_minutes=60,
                    category=ActivityCategory.SHOPPING,
                    estimated_cost_inr=_fallback_slot_cost(
                        ActivityCategory.SHOPPING,
                        distance_km=distance_km,
                        vehicle_type=vehicle_type,
                        is_travel_day=False,
                        is_return_day=False,
                    ),
                    tips="Set a spending limit before entering the market.",
                ),
                _slot(
                    time="07:30 PM",
                    activity=f"Dinner at {dinner_place}",
                    location=destination,
                    description="Enjoy dinner after a full sightseeing day.",
                    duration_minutes=60,
                    category=ActivityCategory.DINNER,
                    estimated_cost_inr=_fallback_slot_cost(
                        ActivityCategory.DINNER,
                        distance_km=distance_km,
                        vehicle_type=vehicle_type,
                        is_travel_day=False,
                        is_return_day=False,
                    ),
                    tips="Reserve a table if the destination is busy.",
                ),
                _slot(
                    time="09:00 PM",
                    activity=f"Return to {hotel_name}",
                    location=destination,
                    description="Head back to the hotel and unwind for the evening.",
                    duration_minutes=30,
                    category=ActivityCategory.HOTEL,
                    estimated_cost_inr=_fallback_slot_cost(
                        ActivityCategory.HOTEL,
                        distance_km=distance_km,
                        vehicle_type=vehicle_type,
                        is_travel_day=False,
                        is_return_day=False,
                    ),
                    tips="Use this time to set out things for tomorrow's schedule.",
                ),
            ]
            day_title = f"Sightseeing Day - {destination}"
            summary = f"Spend the day exploring {destination} with food stops, attractions, and a relaxed evening."
            highlights = [
                f"Morning visit to {attraction_one}",
                f"Afternoon exploration of {attraction_two}",
                "Evening market and dinner time",
            ]

        day_total = round(sum(slot.estimated_cost_inr for slot in slots), 2)
        total_cost += day_total
        generated_days.append(
            DayItinerary(
                day_number=day_number,
                date=current_date.strftime("%d %b %Y"),
                day_title=day_title,
                summary=summary,
                location=destination if not is_travel_day else f"{origin} to {destination}",
                time_slots=slots,
                day_total_cost_inr=day_total,
                distance_km=distance_km if day_number == 1 else 0,
                driving_hours=duration_hours if day_number in (1, trip_days) else 0,
                highlights=highlights[:3],
            )
        )

    try:
        return FullItinerary(
            trip_id=str(state.get("trip_id", "")),
            origin=origin,
            destination=destination,
            total_days=trip_days,
            start_date=start_date.strftime("%d %b %Y"),
            end_date=(start_date + timedelta(days=trip_days - 1)).strftime("%d %b %Y"),
            days=generated_days,
            total_itinerary_cost_inr=round(total_cost, 2),
            generated_at=datetime.now().strftime("%d %b %Y %I:%M %p"),
            travel_tips=travel_tips,
        )
    finally:
        _reset_active_place_pools(token)


def _location_key(value: Any) -> str:
    return _normalize_text(value).casefold()


def _recommendation_map(recommendations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for block in recommendations:
        if not isinstance(block, dict):
            continue
        location = _location_key(block.get("location"))
        if location:
            mapping[location] = block
    return mapping


def _destination_explorer_to_block(destination: str, explorer: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(explorer, dict):
        return None

    def _clean(items: Any, category: str) -> list[dict[str, Any]]:
        if not isinstance(items, list):
            return []
        cleaned: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            name = _normalize_text(item.get("name"))
            normalized = normalize_place_name(name)
            if not name or not normalized or normalized in seen:
                continue
            seen.add(normalized)
            cleaned.append(
                {
                    "name": name,
                    "description": _normalize_text(item.get("reason")) or _normalize_text(item.get("description")),
                    "best_time_to_visit": _normalize_text(item.get("best_time_to_visit")),
                    "cluster": category,
                    "nearby_places": [],
                    "latitude": item.get("latitude"),
                    "longitude": item.get("longitude"),
                    "fallback_generated": bool(item.get("fallback_generated", False)),
                }
            )
        return cleaned

    block = {
        "location": destination,
        "hotels": _clean(explorer.get("hotels"), "Hotels"),
        "restaurants": _clean(explorer.get("restaurants"), "Restaurants"),
        "attractions": _clean(
            [
                *(explorer.get("top_attractions") or []),
                *(explorer.get("hidden_gems") or []),
                *(explorer.get("scenic_places") or []),
                *(explorer.get("rainy_day_places") or []),
                *(explorer.get("evening_places") or []),
            ],
            "Attractions",
        ),
    }
    if not block["hotels"] and not block["restaurants"] and not block["attractions"]:
        return None
    return block


def _explorer_bucket_items(explorer: dict[str, Any] | None, bucket: str) -> list[dict[str, Any]]:
    if not isinstance(explorer, dict):
        return []
    items = explorer.get(bucket, []) or []
    if not isinstance(items, list):
        return []
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        name = _normalize_text(item.get("name"))
        normalized = normalize_place_name(name)
        if not name or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(item)
    return cleaned


def _explorer_attraction_names(explorer: dict[str, Any] | None, day_kind: str, day_index: int) -> list[str]:
    top = _explorer_bucket_items(explorer, "top_attractions")
    hidden = _explorer_bucket_items(explorer, "hidden_gems")
    scenic = _explorer_bucket_items(explorer, "scenic_places")
    evening = _explorer_bucket_items(explorer, "evening_places")
    rainy = _explorer_bucket_items(explorer, "rainy_day_places")

    ordered: list[dict[str, Any]] = []
    if day_kind == "arrival":
        ordered.extend(top[:2] or scenic[:1])
        ordered.extend(evening[:1])
    elif day_kind == "return":
        ordered.extend(scenic[:2] or top[:1])
        ordered.extend(hidden[:1])
    else:
        if day_index % 2 == 0:
            ordered.extend(top[:2])
            ordered.extend(hidden[:1])
            ordered.extend(scenic[:1])
            ordered.extend(evening[:1])
        else:
            ordered.extend(top[:1])
            ordered.extend(scenic[:2])
            ordered.extend(hidden[:1])
            ordered.extend(evening[:1])
        if len(ordered) < 4:
            ordered.extend(rainy[: 4 - len(ordered)])

    names: list[str] = []
    seen: set[str] = set()
    for item in ordered:
        name = _normalize_text(item.get("name"))
        normalized = normalize_place_name(name)
        if not name or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        names.append(name)
    return names


def _explorer_clustered_attractions(explorer: dict[str, Any] | None, day_kind: str, day_index: int) -> list[dict[str, Any]]:
    if not isinstance(explorer, dict):
        return []

    candidates: list[dict[str, Any]] = []
    for bucket in ("top_attractions", "hidden_gems", "scenic_places", "evening_places", "rainy_day_places"):
        items = explorer.get(bucket, []) or []
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    candidates.append(item)

    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in candidates:
        name = _normalize_text(item.get("name"))
        normalized = normalize_place_name(name)
        if not name or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(item)

    if not unique:
        return []

    clusters = cluster_places_by_distance(unique, max_distance_km=5)
    cluster_count = len(clusters)
    places_per_cluster = [len(cluster.get("places", [])) for cluster in clusters]
    average_distance = round(
        sum(float(cluster.get("average_distance_km") or 0.0) for cluster in clusters) / max(cluster_count, 1),
        3,
    )
    logger.info(
        "[ITINERARY] cluster_count=%d places_per_cluster=%s average_distance=%.3f",
        cluster_count,
        places_per_cluster,
        average_distance,
    )

    preferred_cluster_order = {
        "arrival": ["Evening Cluster", "Afternoon Cluster", "Morning Cluster"],
        "return": ["Morning Cluster", "Afternoon Cluster", "Evening Cluster"],
        "full": ["Morning Cluster", "Afternoon Cluster", "Evening Cluster"],
    }.get(day_kind, ["Morning Cluster", "Afternoon Cluster", "Evening Cluster"])
    cluster_label_map = {index: preferred_cluster_order[min(index, len(preferred_cluster_order) - 1)] for index in range(max(cluster_count, 1))}

    ordered_clusters = []
    for index, cluster in enumerate(clusters):
        places = [place for place in cluster.get("places", []) if isinstance(place, dict)]
        if not places:
            continue
        rank = min(_best_time_rank(place.get("best_time_to_visit")) for place in places)
        ordered_clusters.append((preferred_cluster_order.index(cluster_label_map.get(index, preferred_cluster_order[-1])), rank, -len(places), index, cluster))
    ordered_clusters.sort(key=lambda item: (item[0], item[1], item[2]))

    target_count = 2 if day_kind == "arrival" else 3 if day_kind == "return" else 5

    ordered_places: list[dict[str, Any]] = []
    previous_coords: tuple[float | None, float | None] = (None, None)
    for _, _, _, index, cluster in ordered_clusters:
        cluster_label = cluster_label_map.get(index, preferred_cluster_order[-1])
        places = sort_places_nearest_neighbor([place for place in cluster.get("places", []) if isinstance(place, dict)])
        for place in places:
            normalized = normalize_place_name(place.get("name", ""))
            if not normalized or any(normalize_place_name(item.get("name", "")) == normalized for item in ordered_places):
                continue
            place_lat, place_lon = _place_lat_lon(place)
            distance_from_previous = 0.0
            if previous_coords[0] is not None and previous_coords[1] is not None and place_lat is not None and place_lon is not None:
                distance_from_previous = haversine_distance_km(previous_coords[0], previous_coords[1], place_lat, place_lon)
            annotated = dict(place)
            annotated["cluster"] = cluster_label
            annotated["best_time_to_visit"] = annotated.get("best_time_to_visit") or cluster_label.replace(" Cluster", "")
            annotated["distance_from_previous_km"] = round(distance_from_previous, 3)
            annotated["travel_time_minutes"] = estimate_travel_time_minutes(distance_from_previous)
            ordered_places.append(annotated)
            previous_coords = (place_lat, place_lon)
            if len(ordered_places) >= target_count:
                return ordered_places

    if len(ordered_places) < target_count:
        for place in sort_places_nearest_neighbor(unique):
            normalized = normalize_place_name(place.get("name", ""))
            if not normalized or any(normalize_place_name(item.get("name", "")) == normalized for item in ordered_places):
                continue
            place_lat, place_lon = _place_lat_lon(place)
            distance_from_previous = 0.0
            if previous_coords[0] is not None and previous_coords[1] is not None and place_lat is not None and place_lon is not None:
                distance_from_previous = haversine_distance_km(previous_coords[0], previous_coords[1], place_lat, place_lon)
            annotated = dict(place)
            annotated.setdefault("cluster", preferred_cluster_order[min(len(ordered_places), len(preferred_cluster_order) - 1)])
            annotated.setdefault("best_time_to_visit", annotated.get("cluster", "").replace(" Cluster", ""))
            annotated["distance_from_previous_km"] = round(distance_from_previous, 3)
            annotated["travel_time_minutes"] = estimate_travel_time_minutes(distance_from_previous)
            ordered_places.append(annotated)
            previous_coords = (place_lat, place_lon)
            if len(ordered_places) >= target_count:
                break

    return ordered_places


def _annotate_slot_travel_metrics(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add distance and travel-time metadata between successive slots."""
    annotated: list[dict[str, Any]] = []
    previous_coords: tuple[float | None, float | None] = (None, None)

    for slot in slots:
        slot_copy = dict(slot)
        slot_lat_lon = _place_lat_lon(slot_copy)
        distance = 0.0
        if previous_coords[0] is not None and previous_coords[1] is not None and slot_lat_lon[0] is not None and slot_lat_lon[1] is not None:
            distance = haversine_distance_km(previous_coords[0], previous_coords[1], slot_lat_lon[0], slot_lat_lon[1])
        existing_travel_time = _safe_float(slot_copy.get("travel_time_minutes"), 0.0)
        computed_travel_time = estimate_travel_time_minutes(distance)
        if distance <= 0:
            computed_travel_time = int(existing_travel_time or 0)
        else:
            computed_travel_time = max(int(existing_travel_time or 0), computed_travel_time)
        slot_copy["distance_from_previous_km"] = round(distance, 3)
        slot_copy["travel_time_minutes"] = computed_travel_time
        annotated.append(slot_copy)
        if slot_lat_lon[0] is not None and slot_lat_lon[1] is not None:
            previous_coords = slot_lat_lon

    return annotated


def _names_from_block(block: dict[str, Any] | None, kind: str) -> list[str]:
    if not block:
        return []
    items = block.get(kind, [])
    if not isinstance(items, list):
        return []
    names = [_normalize_text(item.get("name")) for item in items if isinstance(item, dict)]
    return [name for name in names if name]


def _pick_place_name(
    *,
    block: dict[str, Any] | None,
    kind: str,
    fallback: str,
    index: int = 0,
) -> str:
    names = _names_from_block(block, kind)
    if names:
        return names[index % len(names)]
    return fallback


def _route_side_stop_name(origin: str, destination: str, waypoints: list[str], index: int = 0) -> str:
    if waypoints:
        return _normalize_text(waypoints[min(index, len(waypoints) - 1)])
    if origin and destination:
        return f"{origin}-{destination} Highway Stop"
    return "Highway Stop"


def _activity_category(value: str) -> ActivityCategory:
    return _category_from_value(value)


def _make_time_slot(
    *,
    time: str,
    type_: ActivityCategory,
    title: str,
    location: str,
    latitude: float | None = None,
    longitude: float | None = None,
    estimated_duration_minutes: int,
    cost_inr: float,
    reason: str,
    travel_time_minutes: int | None = None,
    current_location_before: str,
    current_location_after: str,
    activity: str = "",
    description: str = "",
    place_name: str = "",
    best_time_to_visit: str = "",
    nearby_places: list[str] | None = None,
    distance_from_previous_km: float | None = None,
    cluster: str = "",
) -> TimeSlot:
    return TimeSlot(
        time=time,
        type=type_,
        title=title,
        location=location,
        latitude=latitude,
        longitude=longitude,
        estimated_duration_minutes=max(5, estimated_duration_minutes),
        cost_inr=max(0.0, round(cost_inr, 2)),
        reason=reason,
        travel_time_minutes=travel_time_minutes,
        current_location_before=current_location_before,
        current_location_after=current_location_after,
        activity=activity or title,
        description=description or reason,
        duration_minutes=max(5, estimated_duration_minutes),
        category=type_,
        estimated_cost_inr=max(0.0, round(cost_inr, 2)),
        tips=reason,
        place_name=place_name,
        best_time_to_visit=best_time_to_visit,
        cluster=cluster,
        nearby_places=nearby_places or [],
        distance_from_previous_km=distance_from_previous_km,
    )


def _repair_slot_location(
    *,
    slot_type: ActivityCategory,
    location: str,
    progress: float,
    origin: str,
    destination: str,
    route_stop: str,
) -> str:
    location = _normalize_text(location)
    origin_key = _location_key(origin)
    destination_key = _location_key(destination)
    route_stop = _normalize_text(route_stop)

    if slot_type == ActivityCategory.BREAKFAST and progress < 0.2:
        return origin or location

    if slot_type == ActivityCategory.HOTEL:
        return destination or location

    if slot_type in {ActivityCategory.LUNCH, ActivityCategory.FUEL, ActivityCategory.REST} and progress < 0.9:
        if location.casefold() == destination_key or not location:
            return route_stop or origin or location

    if slot_type in {ActivityCategory.LUNCH, ActivityCategory.DINNER, ActivityCategory.ATTRACTION, ActivityCategory.SIGHTSEEING}:
        if progress < 0.9 and location.casefold() == destination_key:
            return route_stop or origin or location

    if not location:
        return route_stop or origin or destination

    if progress < 0.9 and location.casefold() == destination_key:
        return route_stop or origin or location

    if progress < 0.2 and location.casefold() not in {origin_key, origin_key + " nearby"}:
        if slot_type != ActivityCategory.DRIVE:
            return origin or location

    return location


def _build_route_aware_itinerary(
    *,
    state: TripState,
    origin: str,
    destination: str,
    start_date: datetime,
    trip_days: int,
    budget: float,
    vehicle_type: str,
    number_of_people: int,
    distance_km: float,
    duration_hours: float,
    recommendations: list[dict[str, Any]],
    waypoints: list[str],
) -> FullItinerary:
    rec_map = _recommendation_map(recommendations)
    origin_block = rec_map.get(_location_key(origin))
    destination_block = _destination_explorer_to_block(destination, state.get("destination_explorer")) or rec_map.get(_location_key(destination))
    waypoint_blocks = [rec_map.get(_location_key(item)) for item in waypoints if _location_key(item)]
    route_stop = _route_side_stop_name(origin, destination, waypoints, 0)
    route_stop_two = _route_side_stop_name(origin, destination, waypoints, 1)
    lunch_stop = route_stop_two if len(waypoints) > 1 else route_stop

    place_pools = {
        _location_key(origin): _build_destination_place_pool(origin, recommendations=origin_block, allow_llm=False),
        _location_key(route_stop): _build_destination_place_pool(route_stop, recommendations=waypoint_blocks[0] if waypoint_blocks else None, allow_llm=False),
        _location_key(lunch_stop): _build_destination_place_pool(lunch_stop, recommendations=waypoint_blocks[1] if len(waypoint_blocks) > 1 else (waypoint_blocks[0] if waypoint_blocks else None), allow_llm=False),
        _location_key(destination): _build_destination_place_pool(destination, recommendations=destination_block, allow_llm=True),
    }
    token = _set_active_place_pools(place_pools)
    used_places: set[str] = set()

    origin_breakfast = get_unique_place("restaurants", origin, used_places)
    route_lunch = get_unique_place("restaurants", lunch_stop, used_places)
    route_fuel = get_unique_place("fuel_stops", route_stop, used_places)
    route_rest = get_unique_place("rest_stops", route_stop, used_places)
    destination_hotel = get_unique_place("hotels", destination, used_places)
    destination_dinner = get_unique_place("restaurants", destination, used_places)

    travel_tips = [
        "Start early so the first meal and the main drive both happen before traffic builds up.",
        "Keep food and fuel stops on the route until the arrival checkpoint is complete.",
        "Use the destination only after check-in for restaurants, attractions, and dinner.",
        "If the road trip runs long, use the nearest waypoint or highway town instead of pushing into the destination early.",
        "Carry water, cash or UPI, and a phone charger for every long driving stretch.",
    ]

    def route_day_slot_plan() -> list[dict[str, Any]]:
        return _annotate_slot_travel_metrics([
            {
                "time": "06:30 AM",
                "type": ActivityCategory.BREAKFAST,
                "title": f"Breakfast at {origin_breakfast.get('name', 'Origin Breakfast Stop')}",
                "location": origin,
                "estimated_duration_minutes": 30,
                "cost_inr": _fallback_slot_cost(
                    ActivityCategory.BREAKFAST,
                    distance_km=distance_km,
                    vehicle_type=vehicle_type,
                    is_travel_day=True,
                    is_return_day=False,
                ),
                "reason": "Eat near the origin before the first driving stretch begins.",
                "current_location_before": origin,
                "current_location_after": origin,
                "progress": 0.05,
            },
            {
                "time": "07:15 AM",
                "type": ActivityCategory.DRIVE,
                "title": f"Drive from {origin} toward {destination}",
                "location": route_stop if waypoints else origin,
                "estimated_duration_minutes": max(60, int(max(duration_hours, 1.0) * 60 * 0.38)),
                "cost_inr": 0.0,
                "reason": "Cover the first long highway leg while the traveler is still fresh.",
                "current_location_before": origin,
                "current_location_after": route_stop,
                "progress": 0.25,
            },
            {
                "time": "10:45 AM",
                "type": ActivityCategory.FUEL,
                "title": f"Fuel and tea stop at {route_fuel.get('name', route_stop)}",
                "location": route_stop,
                "estimated_duration_minutes": 25,
                "cost_inr": _fallback_slot_cost(
                    ActivityCategory.FUEL,
                    distance_km=distance_km,
                    vehicle_type=vehicle_type,
                    is_travel_day=True,
                    is_return_day=False,
                ),
                "reason": "Refuel and stretch at a route-side town before the next leg.",
                "current_location_before": route_stop,
                "current_location_after": route_stop,
                "progress": 0.35,
            },
            {
                "time": "01:00 PM",
                "type": ActivityCategory.LUNCH,
                "title": f"Lunch at {route_lunch.get('name', lunch_stop)}",
                "location": lunch_stop,
                "estimated_duration_minutes": 45,
                "cost_inr": _fallback_slot_cost(
                    ActivityCategory.LUNCH,
                    distance_km=distance_km,
                    vehicle_type=vehicle_type,
                    is_travel_day=True,
                    is_return_day=False,
                ),
                "reason": "Have lunch at a route-side town instead of entering the destination too early.",
                "current_location_before": route_stop,
                "current_location_after": route_stop,
                "progress": 0.55,
            },
            {
                "time": "02:00 PM",
                "type": ActivityCategory.DRIVE,
                "title": f"Final drive into {destination}",
                "location": destination,
                "estimated_duration_minutes": max(75, int(max(duration_hours, 1.0) * 60 * 0.45)),
                "cost_inr": 0.0,
                "reason": "Complete the last stretch only after the route-side meal break.",
                "current_location_before": route_stop,
                "current_location_after": destination,
                "progress": 0.92,
            },
            {
                "time": "05:30 PM",
                "type": ActivityCategory.HOTEL,
                "title": f"Check in at {destination_hotel.get('name', destination)}",
                "location": destination,
                "estimated_duration_minutes": 40,
                "cost_inr": _fallback_slot_cost(
                    ActivityCategory.HOTEL,
                    distance_km=distance_km,
                    vehicle_type=vehicle_type,
                    is_travel_day=True,
                    is_return_day=False,
                ),
                "reason": "Check in only after arrival so the hotel stay follows the completed journey.",
                "current_location_before": destination,
                "current_location_after": destination,
                "progress": 1.0,
            },
            {
                "time": "08:00 PM",
                "type": ActivityCategory.DINNER,
                "title": f"Dinner at {destination_dinner.get('name', destination)}",
                "location": destination,
                "estimated_duration_minutes": 60,
                "cost_inr": _fallback_slot_cost(
                    ActivityCategory.DINNER,
                    distance_km=distance_km,
                    vehicle_type=vehicle_type,
                    is_travel_day=True,
                    is_return_day=False,
                ),
                "reason": "Dinner happens after arrival and check-in, never before the destination is reached.",
                "current_location_before": destination,
                "current_location_after": destination,
                "progress": 1.0,
            },
        ])

    def destination_day_slot_plan(day_index: int) -> list[dict[str, Any]]:
        breakfast_place = get_unique_place("restaurants", destination, used_places)
        lunch_place = get_unique_place("restaurants", destination, used_places)
        dinner_place = get_unique_place("restaurants", destination, used_places)
        attraction_title = get_unique_place("attractions", destination, used_places).get("name", destination)
        secondary_attraction = get_unique_place("attractions", destination, used_places).get("name", destination)
        return _annotate_slot_travel_metrics([
            {
                "time": "08:00 AM",
                "type": ActivityCategory.BREAKFAST,
                "title": f"Breakfast at {breakfast_place.get('name', destination)}",
                "location": destination,
                "estimated_duration_minutes": 40,
                "cost_inr": _fallback_slot_cost(
                    ActivityCategory.BREAKFAST,
                    distance_km=distance_km,
                    vehicle_type=vehicle_type,
                    is_travel_day=False,
                    is_return_day=False,
                ),
                "reason": "Start the day in the destination after arrival and overnight stay.",
                "current_location_before": destination,
                "current_location_after": destination,
                "progress": 1.0,
            },
            {
                "time": "09:30 AM",
                "type": ActivityCategory.ATTRACTION,
                "title": f"Visit {attraction_title}",
                "location": destination,
                "estimated_duration_minutes": 120,
                "cost_inr": _fallback_slot_cost(
                    ActivityCategory.ATTRACTION,
                    distance_km=distance_km,
                    vehicle_type=vehicle_type,
                    is_travel_day=False,
                    is_return_day=False,
                ),
                "reason": "Sightseeing belongs after arrival, once the traveler is settled in the destination.",
                "current_location_before": destination,
                "current_location_after": destination,
                "progress": 1.0,
            },
            {
                "time": "12:30 PM",
                "type": ActivityCategory.LUNCH,
                "title": f"Lunch at {lunch_place.get('name', destination)}",
                "location": destination,
                "estimated_duration_minutes": 60,
                "cost_inr": _fallback_slot_cost(
                    ActivityCategory.LUNCH,
                    distance_km=distance_km,
                    vehicle_type=vehicle_type,
                    is_travel_day=False,
                    is_return_day=False,
                ),
                "reason": "Lunch can now be scheduled in the destination because arrival is already complete.",
                "current_location_before": destination,
                "current_location_after": destination,
                "progress": 1.0,
            },
            {
                "time": "03:00 PM",
                "type": ActivityCategory.ATTRACTION,
                "title": f"Explore {secondary_attraction}",
                "location": destination,
                "estimated_duration_minutes": 120,
                "cost_inr": _fallback_slot_cost(
                    ActivityCategory.ATTRACTION,
                    distance_km=distance_km,
                    vehicle_type=vehicle_type,
                    is_travel_day=False,
                    is_return_day=False,
                ),
                "reason": "Use the afternoon for destination-based attractions after the traveler has arrived.",
                "current_location_before": destination,
                "current_location_after": destination,
                "progress": 1.0,
            },
            {
                "time": "07:30 PM",
                "type": ActivityCategory.DINNER,
                "title": f"Dinner at {dinner_place.get('name', destination)}",
                "location": destination,
                "estimated_duration_minutes": 60,
                "cost_inr": _fallback_slot_cost(
                    ActivityCategory.DINNER,
                    distance_km=distance_km,
                    vehicle_type=vehicle_type,
                    is_travel_day=False,
                    is_return_day=False,
                ),
                "reason": "Dinner stays in the destination because the traveler is already checked in.",
                "current_location_before": destination,
                "current_location_after": destination,
                "progress": 1.0,
            },
            {
                "time": "09:00 PM",
                "type": ActivityCategory.HOTEL,
                "title": f"Return to {destination_hotel.get('name', destination)}",
                "location": destination,
                "estimated_duration_minutes": 30,
                "cost_inr": _fallback_slot_cost(
                    ActivityCategory.HOTEL,
                    distance_km=distance_km,
                    vehicle_type=vehicle_type,
                    is_travel_day=False,
                    is_return_day=False,
                ),
                "reason": "Hotel time comes only after the arrival and dining steps are complete.",
                "current_location_before": destination,
                "current_location_after": destination,
                "progress": 1.0,
            },
        ])

    def return_day_slot_plan() -> list[dict[str, Any]]:
        breakfast_place = get_unique_place("restaurants", destination, used_places)
        lunch_place = get_unique_place("restaurants", destination, used_places)
        attraction_place = get_unique_place("attractions", destination, used_places)
        return [
            {
                "time": "08:00 AM",
                "type": ActivityCategory.BREAKFAST,
                "title": f"Breakfast at {breakfast_place.get('name', destination)}",
                "location": destination,
                "estimated_duration_minutes": 40,
                "cost_inr": _fallback_slot_cost(
                    ActivityCategory.BREAKFAST,
                    distance_km=distance_km,
                    vehicle_type=vehicle_type,
                    is_travel_day=False,
                    is_return_day=True,
                ),
                "reason": "Begin the return day from the destination after the overnight stay.",
                "current_location_before": destination,
                "current_location_after": destination,
                "progress": 1.0,
            },
            {
                "time": "09:30 AM",
                "type": ActivityCategory.ATTRACTION,
                "title": f"Final stop at {attraction_place.get('name', destination)}",
                "location": destination,
                "estimated_duration_minutes": 90,
                "cost_inr": _fallback_slot_cost(
                    ActivityCategory.ATTRACTION,
                    distance_km=distance_km,
                    vehicle_type=vehicle_type,
                    is_travel_day=False,
                    is_return_day=True,
                ),
                "reason": "A short destination stop works before the return drive begins.",
                "current_location_before": destination,
                "current_location_after": destination,
                "progress": 1.0,
            },
            {
                "time": "11:30 AM",
                "type": ActivityCategory.DRIVE,
                "title": f"Drive back to {origin}",
                "location": origin,
                "estimated_duration_minutes": max(60, int(max(duration_hours, 1.0) * 60 * 0.55)),
                "cost_inr": 0.0,
                "reason": "Start the long return drive only after the destination morning activities are complete.",
                "current_location_before": destination,
                "current_location_after": route_stop,
                "progress": 0.45,
            },
            {
                "time": "02:00 PM",
                "type": ActivityCategory.LUNCH,
                "title": f"Lunch at {lunch_place.get('name', lunch_stop)}",
                "location": route_stop,
                "estimated_duration_minutes": 45,
                "cost_inr": _fallback_slot_cost(
                    ActivityCategory.LUNCH,
                    distance_km=distance_km,
                    vehicle_type=vehicle_type,
                    is_travel_day=False,
                    is_return_day=True,
                ),
                "reason": "Lunch should happen on the route, not back in the destination once the return has begun.",
                "current_location_before": route_stop,
                "current_location_after": route_stop,
                "progress": 0.65,
            },
            {
                "time": "04:30 PM",
                "type": ActivityCategory.FUEL,
                "title": f"Fuel and tea break at {route_rest.get('name', route_stop)}",
                "location": route_stop,
                "estimated_duration_minutes": 25,
                "cost_inr": _fallback_slot_cost(
                    ActivityCategory.FUEL,
                    distance_km=distance_km,
                    vehicle_type=vehicle_type,
                    is_travel_day=False,
                    is_return_day=True,
                ),
                "reason": "A route-side fuel and tea stop keeps the final stretch safe and realistic.",
                "current_location_before": route_stop,
                "current_location_after": route_stop,
                "progress": 0.8,
            },
            {
                "time": "07:30 PM",
                "type": ActivityCategory.REST,
                "title": "Arrive back home",
                "location": origin,
                "estimated_duration_minutes": 30,
                "cost_inr": 0.0,
                "reason": "The trip ends only after the traveler has returned to the origin city.",
                "current_location_before": route_stop,
                "current_location_after": origin,
                "progress": 1.0,
            },
        ]

    day_plans: list[list[dict[str, Any]]] = []
    for day_number in range(1, trip_days + 1):
        if day_number == 1:
            day_plans.append(route_day_slot_plan())
        elif trip_days >= 3 and day_number == trip_days:
            day_plans.append(return_day_slot_plan())
        else:
            day_plans.append(destination_day_slot_plan(day_number))

    total_cost = 0.0
    days: list[DayItinerary] = []
    for day_index, slot_plan in enumerate(day_plans):
        day_number = day_index + 1
        day_date = start_date + timedelta(days=day_index)
        day_slots: list[TimeSlot] = []
        day_cost = 0.0
        previous_location = origin if day_number == 1 else destination

        for raw_slot in slot_plan:
            slot_type = _activity_category(raw_slot.get("type", "misc"))
            progress = _safe_float(raw_slot.get("progress"), 1.0)
            location = _repair_slot_location(
                slot_type=slot_type,
                location=_normalize_text(raw_slot.get("location")),
                progress=progress,
                origin=origin,
                destination=destination,
                route_stop=route_stop,
            )
            current_before = _normalize_text(raw_slot.get("current_location_before"), previous_location)
            current_after = _normalize_text(raw_slot.get("current_location_after"), location)

            if slot_type == ActivityCategory.DRIVE:
                current_before = previous_location
                current_after = location
            elif slot_type == ActivityCategory.HOTEL and progress < 0.9:
                location = destination
                current_before = destination
                current_after = destination

            title = _normalize_text(raw_slot.get("title"))
            if slot_type == ActivityCategory.BREAKFAST and progress < 0.2:
                location = origin or location
            if slot_type in {ActivityCategory.LUNCH, ActivityCategory.FUEL} and progress < 0.9 and location.casefold() == _location_key(destination):
                location = route_stop

            cost = _safe_float(raw_slot.get("cost_inr"), 0.0)
            slot = _make_time_slot(
                time=_normalize_text(raw_slot.get("time")),
                type_=slot_type,
                title=title,
                location=location,
                estimated_duration_minutes=_safe_int(raw_slot.get("estimated_duration_minutes"), 30),
                cost_inr=cost,
                reason=_normalize_text(raw_slot.get("reason")),
                current_location_before=current_before,
                current_location_after=current_after,
                activity=_normalize_text(raw_slot.get("activity"), title),
                description=_normalize_text(raw_slot.get("description"), _normalize_text(raw_slot.get("reason"))),
                distance_from_previous_km=_safe_float(raw_slot.get("distance_from_previous_km"), 0.0) or None,
                cluster=_normalize_text(raw_slot.get("cluster")),
            )
            day_slots.append(slot)
            day_cost += slot.cost_inr
            previous_location = slot.current_location_after or location

        if day_number == 1:
            day_location = f"{origin} to {destination}"
            distance_today = distance_km
            driving_today = duration_hours
            day_title = f"Departure Day - {origin} to {destination}"
            summary = f"Travel from {origin} to {destination} with route-side stops before check-in."
            highlights = [
                f"Breakfast near {origin}",
                f"Fuel and lunch at {route_stop}",
                f"Hotel check-in and dinner in {destination}",
            ]
        elif trip_days >= 3 and day_number == trip_days:
            day_location = origin
            distance_today = distance_km
            driving_today = duration_hours
            day_title = f"Return Day - {destination} to {origin}"
            summary = f"Wrap up the destination stay and return to {origin} with route-side breaks."
            highlights = [
                f"Morning stop in {destination}",
                f"Lunch and fuel on the route",
                f"Arrive back at {origin}",
            ]
        else:
            day_location = destination
            distance_today = 0
            driving_today = 0
            day_title = f"Day {day_number} in {destination}"
            summary = f"Spend the day in {destination} after arrival, with meals and attractions nearby."
            highlights = [
                f"Destination breakfast in {destination}",
                f"Local sightseeing and lunch",
                f"Evening dinner and hotel time",
            ]

        total_cost += day_cost
        days.append(
            DayItinerary(
                day_number=day_number,
                date=day_date.strftime("%d %b %Y"),
                day_title=day_title,
                summary=summary,
                location=day_location,
                time_slots=day_slots,
                day_total_cost_inr=round(day_cost, 2),
                distance_km=distance_today,
                driving_hours=driving_today,
                highlights=highlights,
            )
        )

    before_validation_places = _itinerary_place_names(days)
    before_duplicates = len(before_validation_places) - len(set(before_validation_places))
    days = _validate_unique_itinerary_places(days)
    after_validation_places = _itinerary_place_names(days)
    after_duplicates = len(after_validation_places) - len(set(after_validation_places))
    logger.info(
        "[ITINERARY] duplicate validation before=%d after=%d",
        before_duplicates,
        after_duplicates,
    )
    logger.info(
        "[ITINERARY] final selected places=%s",
        [
            {
                "day": day.day_number,
                "places": [slot.place_name or slot.title or slot.activity for slot in day.time_slots if slot.type in {ActivityCategory.BREAKFAST, ActivityCategory.LUNCH, ActivityCategory.DINNER, ActivityCategory.ATTRACTION, ActivityCategory.SIGHTSEEING, ActivityCategory.HOTEL, ActivityCategory.FUEL}],
            }
            for day in days
        ],
    )
    return FullItinerary(
        trip_id=str(state.get("trip_id", "")),
        origin=origin,
        destination=destination,
        total_days=trip_days,
        start_date=start_date.strftime("%d %b %Y"),
        end_date=(start_date + timedelta(days=trip_days - 1)).strftime("%d %b %Y"),
        days=days,
        total_itinerary_cost_inr=round(total_cost, 2),
        generated_at=datetime.now().strftime("%d %b %Y %I:%M %p"),
        travel_tips=travel_tips,
    )


def _build_prompt(
    *,
    origin: str,
    destination: str,
    dates: str,
    trip_days: int,
    budget: float,
    vehicle_type: str,
    number_of_people: int,
    distance_km: float,
    duration_hours: float,
    is_vegetarian: bool,
    is_budget: bool,
    hotel_names: list[str],
    restaurant_names: list[str],
    attraction_names: list[str],
    weather_context: str,
) -> str:
    start_label = _normalize_text(dates.split(" to ", 1)[0] if " to " in dates else dates)
    return f"""
You are a professional Indian travel itinerary planner.
Create a detailed day-by-day travel itinerary.

TRIP DETAILS:
- Origin: {origin}
- Destination: {destination}
- Duration: {trip_days} days
- Vehicle: {vehicle_type}
- People: {number_of_people}
- Total Budget: Rs.{budget:,.0f}
- Distance: {distance_km} km
- Drive Time: {duration_hours} hours
- Food Preference: {'Vegetarian' if is_vegetarian else 'Non-Vegetarian'}
- Budget conscious: {is_budget}

AVAILABLE HOTELS IN {destination}:
{', '.join(hotel_names) if hotel_names else 'Various hotels available'}

RESTAURANTS IN {destination}:
{', '.join(restaurant_names) if restaurant_names else 'Various restaurants available'}

ATTRACTIONS IN {destination}:
{', '.join(attraction_names) if attraction_names else 'Various attractions available'}

WEATHER FORECAST:
{weather_context if weather_context else 'Check local weather'}

RULES:
1. Day 1 is ALWAYS the travel day from {origin} to {destination}
2. Last day is ALWAYS the return journey OR full sightseeing
3. Middle days are for sightseeing at {destination}
4. Include realistic Indian travel timings
5. Include meal breaks (breakfast, lunch, dinner)
6. Include fuel stops for {vehicle_type} trips
7. Use REAL place names in {destination}
8. Costs should be realistic for India in INR
9. Each day should have 6-10 time slots
10. Include pro travel tips for each activity

Return ONLY this exact JSON format, no other text:

{{
  "days": [
    {{
      "day_number": 1,
      "date": "{start_label or '04 Jun 2026'}",
      "day_title": "Departure - {origin} to {destination}",
      "summary": "One sentence summary of the day",
      "location": "{origin} to {destination}",
      "distance_km": {distance_km},
      "driving_hours": {duration_hours},
      "highlights": ["highlight 1", "highlight 2", "highlight 3"],
      "day_total_cost_inr": 500,
      "time_slots": [
        {{
          "time": "07:00 AM",
          "activity": "Early morning breakfast",
          "location": "Home / {origin}",
          "description": "Have a light breakfast before the journey",
          "duration_minutes": 30,
          "category": "breakfast",
          "estimated_cost_inr": 150,
          "tips": "Start early to avoid traffic"
        }}
      ]
    }}
  ],
  "travel_tips": [
    "tip 1",
    "tip 2",
    "tip 3",
    "tip 4",
    "tip 5"
  ]
}}

Generate all {trip_days} days completely.
Make it professional, detailed, and realistic for Indian road travel from {origin} to {destination}.
""".strip()


def _call_llm_with_timeout(prompt: str, temperature: float = 0.7, timeout_seconds: float = 12.0) -> str:
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(call_llm_json, prompt, temperature)
    try:
        return future.result(timeout=timeout_seconds)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def run_itinerary_agent(state: dict) -> dict:
    print("=== ITINERARY AGENT START ===")

    origin = _normalize_text(state.get("origin"))
    destination = _normalize_text(state.get("destination"))
    dates = _normalize_text(state.get("dates"))
    trip_days = max(1, _safe_int(state.get("trip_days"), 1))
    budget = _safe_float(state.get("budget"), 15000.0)
    preferences = state.get("preferences", []) or []
    vehicle = state.get("vehicle", {}) or {}
    vehicle_type = _normalize_text(vehicle.get("vehicle_type"), "car")
    number_of_people = max(1, _safe_int(vehicle.get("number_of_people"), 1))

    recommendations = state.get("recommendations", []) or []
    rec_location = recommendations[0] if recommendations else {}

    hotels = _as_list(rec_location.get("hotels"))
    restaurants = _as_list(rec_location.get("restaurants"))
    attractions = _as_list(rec_location.get("attractions"))

    hotel_names = [_normalize_text(item.get("name")) for item in hotels[:3] if _normalize_text(item.get("name"))]
    restaurant_names = [_normalize_text(item.get("name")) for item in restaurants[:5] if _normalize_text(item.get("name"))]
    attraction_names = [_normalize_text(item.get("name")) for item in attractions[:5] if _normalize_text(item.get("name"))]

    weather = state.get("weather", []) or []
    route = state.get("route", {}) or {}
    distance_km = _safe_float(route.get("distance_km"), 0.0)
    duration_hours = _safe_float(route.get("duration_hours"), 0.0)
    start_date = _parse_start_date(dates)

    weather_context = ""
    if isinstance(weather, list) and weather:
        for i, day in enumerate(weather[:trip_days]):
            if isinstance(day, dict):
                weather_context += f"Day {i + 1}: {day.get('condition', 'Clear')} {day.get('temp_max_celsius', 25)}°C\n"

    is_vegetarian = any("veg" in str(p).lower() for p in preferences)
    is_budget = any("budget" in str(p).lower() for p in preferences)

    print(f"[ITINERARY] Generating {trip_days}-day itinerary: {origin} -> {destination}")

    prompt = _build_prompt(
        origin=origin,
        destination=destination,
        dates=dates,
        trip_days=trip_days,
        budget=budget,
        vehicle_type=vehicle_type,
        number_of_people=number_of_people,
        distance_km=distance_km,
        duration_hours=duration_hours,
        is_vegetarian=is_vegetarian,
        is_budget=is_budget,
        hotel_names=hotel_names,
        restaurant_names=restaurant_names,
        attraction_names=attraction_names,
        weather_context=weather_context,
    )

    try:
        print("[ITINERARY] Calling NVIDIA LLaMA...")
        response = _call_llm_with_timeout(prompt=prompt, temperature=0.7, timeout_seconds=12.0)
        clean = _strip_code_fences(response)
        data = json.loads(clean)
        days_data = data.get("days", []) if isinstance(data, dict) else []
        travel_tips = data.get("travel_tips", []) if isinstance(data, dict) else []

        days: list[DayItinerary] = []
        total_cost = 0.0
        for index, day_data in enumerate(days_data[:trip_days]):
            if not isinstance(day_data, dict):
                continue

            time_slots: list[TimeSlot] = []
            day_cost = 0.0
            for slot_data in day_data.get("time_slots", []):
                if not isinstance(slot_data, dict):
                    continue
                try:
                    category = _category_from_value(slot_data.get("category"))
                    cost = _safe_float(slot_data.get("estimated_cost_inr"), 0.0)
                    cost = _normalize_slot_cost(
                        cost,
                        category,
                        distance_km=distance_km,
                        vehicle_type=vehicle_type,
                        is_travel_day=index == 0,
                        is_return_day=index == trip_days - 1 and trip_days >= 3,
                    )
                    slot = TimeSlot(
                        time=_normalize_text(slot_data.get("time")),
                        activity=_normalize_text(slot_data.get("activity")),
                        location=_normalize_text(slot_data.get("location")),
                        description=_normalize_text(slot_data.get("description")),
                        duration_minutes=max(5, _safe_int(slot_data.get("duration_minutes"), 30)),
                        category=category,
                        estimated_cost_inr=max(0.0, round(cost, 2)),
                        tips=_normalize_text(slot_data.get("tips")),
                    )
                    day_cost += slot.estimated_cost_inr
                    time_slots.append(slot)
                except Exception as exc:
                    print(f"[ITINERARY] Slot error: {exc}")

            if not time_slots:
                continue

            day_date = start_date + timedelta(days=index)
            day_total = _safe_float(day_data.get("day_total_cost_inr"), day_cost)
            if day_cost > 0:
                if day_total <= 0 or day_total > max(15000.0, day_cost * 2.5):
                    day_total = day_cost
            total_cost += day_total
            days.append(
                DayItinerary(
                    day_number=_safe_int(day_data.get("day_number"), index + 1),
                    date=day_date.strftime("%d %b %Y"),
                    day_title=_normalize_text(day_data.get("day_title"), f"Day {index + 1}"),
                    summary=_normalize_text(day_data.get("summary")),
                    location=_normalize_text(day_data.get("location"), destination),
                    time_slots=time_slots,
                    day_total_cost_inr=round(day_total, 2),
                    distance_km=_safe_float(day_data.get("distance_km"), 0.0),
                    driving_hours=_safe_float(day_data.get("driving_hours"), 0.0),
                    highlights=[_normalize_text(item) for item in (day_data.get("highlights") or []) if _normalize_text(item)],
                )
            )

        if len(days) != trip_days:
            raise ValueError("LLM itinerary response did not contain the expected number of days.")

        itinerary = FullItinerary(
            trip_id=str(state.get("trip_id", "")),
            origin=origin,
            destination=destination,
            total_days=trip_days,
            start_date=start_date.strftime("%d %b %Y"),
            end_date=(start_date + timedelta(days=trip_days - 1)).strftime("%d %b %Y"),
            days=days,
            total_itinerary_cost_inr=round(total_cost, 2),
            generated_at=datetime.now().strftime("%d %b %Y %I:%M %p"),
            travel_tips=[_normalize_text(item) for item in travel_tips if _normalize_text(item)],
        )
        state["itinerary"] = itinerary.model_dump(mode="json")
        print("[ITINERARY] Complete!")
        return state
    except Exception as exc:
        print(f"[ITINERARY] Falling back to deterministic itinerary: {exc}")
        itinerary = _build_fallback_itinerary(
            state=state,
            origin=origin,
            destination=destination,
            start_date=start_date,
            trip_days=trip_days,
            budget=budget,
            vehicle_type=vehicle_type,
            distance_km=distance_km,
            duration_hours=duration_hours,
            hotels=hotels,
            restaurants=restaurants,
            attractions=attractions,
        )
        state["itinerary"] = itinerary.model_dump(mode="json")
        print("[ITINERARY] Fallback complete!")
        return state


def _run_route_aware_itinerary_agent(state: dict) -> dict:
    print("=== ITINERARY AGENT START ===")

    origin = _normalize_text(state.get("origin"))
    destination = _normalize_text(state.get("destination"))
    dates = _normalize_text(state.get("dates"))
    trip_days = max(1, _safe_int(state.get("trip_days"), 1))
    budget = _safe_float(state.get("budget"), 15000.0)
    vehicle = state.get("vehicle", {}) or {}
    vehicle_type = _normalize_text(vehicle.get("vehicle_type"), "car")
    number_of_people = max(1, _safe_int(vehicle.get("number_of_people"), 1))
    route = state.get("route", {}) or {}
    distance_km = _safe_float(route.get("distance_km"), 0.0)
    duration_hours = _safe_float(route.get("duration_hours"), 0.0)
    start_date = _parse_start_date(dates)

    waypoints = state.get("waypoints", []) or []
    if not isinstance(waypoints, list):
        waypoints = [waypoints]
    waypoints = [_normalize_text(item) for item in waypoints if _normalize_text(item)]

    recommendations = state.get("recommendations", []) or []
    rec_blocks = [block for block in recommendations if isinstance(block, dict)]

    itinerary = _build_route_aware_itinerary(
        state=state,
        origin=origin,
        destination=destination,
        start_date=start_date,
        trip_days=trip_days,
        budget=budget,
        vehicle_type=vehicle_type,
        number_of_people=number_of_people,
        distance_km=distance_km,
        duration_hours=duration_hours,
        recommendations=rec_blocks,
        waypoints=waypoints,
    )
    state["itinerary"] = itinerary.model_dump(mode="json")
    state["travel_tips"] = itinerary.travel_tips
    print("[ITINERARY] Route-aware complete!")
    return state


OOTY_SIGHTSEEING_ENTRIES: list[dict[str, Any]] = [
    {
        "name": "Government Botanical Garden",
        "description": "A classic botanical garden with seasonal blooms and shaded paths.",
        "best_time_to_visit": "Morning",
        "cluster": "Town Center",
        "nearby_places": ["Rose Garden", "Thread Garden", "Ooty Lake"],
    },
    {
        "name": "Rose Garden",
        "description": "A colorful hillside garden known for its rose varieties.",
        "best_time_to_visit": "Late Morning",
        "cluster": "Town Center",
        "nearby_places": ["Government Botanical Garden", "Thread Garden", "Ooty Lake"],
    },
    {
        "name": "Ooty Lake",
        "description": "A scenic lake for relaxed sightseeing and an evening walk.",
        "best_time_to_visit": "Evening",
        "cluster": "Town Center",
        "nearby_places": ["Charring Cross", "Government Botanical Garden", "Rose Garden"],
    },
    {
        "name": "Doddabetta Peak",
        "description": "The highest peak in the Nilgiris with sweeping hill views.",
        "best_time_to_visit": "Morning",
        "cluster": "Hilltop Loop",
        "nearby_places": ["Tea Museum", "Government Museum", "St Stephen's Church"],
    },
    {
        "name": "Tea Museum",
        "description": "A tea heritage stop with local processing stories and tastings.",
        "best_time_to_visit": "Late Morning",
        "cluster": "Hilltop Loop",
        "nearby_places": ["Doddabetta Peak", "Government Museum", "St Stephen's Church"],
    },
    {
        "name": "Government Museum",
        "description": "A cultural stop for local history and artifacts.",
        "best_time_to_visit": "Afternoon",
        "cluster": "Hilltop Loop",
        "nearby_places": ["Tea Museum", "Thread Garden", "St Stephen's Church"],
    },
    {
        "name": "Thread Garden",
        "description": "An unusual hand-crafted garden attraction in Ooty.",
        "best_time_to_visit": "Afternoon",
        "cluster": "Town Center",
        "nearby_places": ["Government Botanical Garden", "Rose Garden", "Charring Cross"],
    },
    {
        "name": "Charring Cross Evening Walk",
        "description": "A walkable town-center stop for market browsing and an easy evening stroll.",
        "best_time_to_visit": "Evening",
        "cluster": "Town Center",
        "nearby_places": ["Ooty Lake", "Nilgiri Mountain Railway", "St Stephen's Church"],
    },
    {
        "name": "Nilgiri Mountain Railway",
        "description": "A heritage rail experience that is iconic to the region.",
        "best_time_to_visit": "Morning",
        "cluster": "Town Center",
        "nearby_places": ["Government Museum", "St Stephen's Church", "Charring Cross"],
    },
    {
        "name": "St Stephen's Church",
        "description": "A historic church and a quiet architectural stop.",
        "best_time_to_visit": "Late Morning",
        "cluster": "Town Center",
        "nearby_places": ["Government Museum", "Charring Cross", "Nilgiri Mountain Railway"],
    },
    {
        "name": "Pykara Lake",
        "description": "A calm lake stop ideal for a scenic half-day outing.",
        "best_time_to_visit": "Morning",
        "cluster": "Pykara Loop",
        "nearby_places": ["Pykara Waterfalls", "Pine Forest", "Shooting Point"],
    },
    {
        "name": "Pykara Waterfalls",
        "description": "A photogenic waterfall stop on the scenic Pykara route.",
        "best_time_to_visit": "Late Morning",
        "cluster": "Pykara Loop",
        "nearby_places": ["Pykara Lake", "Pine Forest", "Shooting Point"],
    },
    {
        "name": "Pine Forest",
        "description": "A photogenic pine-lined stretch ideal for a peaceful stroll.",
        "best_time_to_visit": "Afternoon",
        "cluster": "Pykara Loop",
        "nearby_places": ["Wenlock Downs", "Shooting Point", "Pykara Lake"],
    },
    {
        "name": "Shooting Point",
        "description": "A scenic viewpoint with sweeping valley views and open skies.",
        "best_time_to_visit": "Afternoon",
        "cluster": "Pykara Loop",
        "nearby_places": ["Wenlock Downs", "Pine Forest", "Pykara Lake"],
    },
    {
        "name": "Wenlock Downs",
        "description": "A wide open grassland viewpoint for a scenic drive and walk.",
        "best_time_to_visit": "Evening",
        "cluster": "Pykara Loop",
        "nearby_places": ["Shooting Point", "Pine Forest", "Pykara Lake"],
    },
    {
        "name": "Avalanche Lake",
        "description": "A quieter lake destination with a more natural setting.",
        "best_time_to_visit": "Afternoon",
        "cluster": "Scenic Loop",
        "nearby_places": ["Emerald Lake", "Toda Huts", "Karnataka Siri Horticulture Garden"],
    },
    {
        "name": "Emerald Lake",
        "description": "A peaceful reservoir-style stop with hill scenery.",
        "best_time_to_visit": "Afternoon",
        "cluster": "Scenic Loop",
        "nearby_places": ["Avalanche Lake", "Toda Huts", "Karnataka Siri Horticulture Garden"],
    },
    {
        "name": "Toda Huts",
        "description": "A local cultural stop with Toda heritage and open landscape views.",
        "best_time_to_visit": "Afternoon",
        "cluster": "Scenic Loop",
        "nearby_places": ["Avalanche Lake", "Emerald Lake", "Karnataka Siri Horticulture Garden"],
    },
    {
        "name": "Karnataka Siri Horticulture Garden",
        "description": "A garden stop with manicured greenery and easy walkable spaces.",
        "best_time_to_visit": "Evening",
        "cluster": "Scenic Loop",
        "nearby_places": ["Toda Huts", "Avalanche Lake", "Emerald Lake"],
    },
    {
        "name": "Upper Bhavani Lake",
        "description": "A remote scenic lake stop for travelers who want a quieter nature detour.",
        "best_time_to_visit": "Morning",
        "cluster": "Remote Scenic",
        "nearby_places": ["Emerald Lake", "Avalanche Lake", "Toda Huts"],
    },
]


OOTY_DAY_THEMES: dict[str, list[str]] = {
    "arrival": ["Government Botanical Garden", "Rose Garden", "Ooty Lake"],
    "core": ["Doddabetta Peak", "Tea Museum", "Government Museum", "Thread Garden", "Charring Cross Evening Walk"],
    "scenic": ["Pykara Lake", "Pykara Waterfalls", "Pine Forest", "Shooting Point", "Wenlock Downs"],
}


def _normalize_place_entry(entry: dict[str, Any]) -> dict[str, Any]:
    item = dict(entry)
    item["name"] = _normalize_text(item.get("name"))
    item["description"] = _normalize_text(item.get("description"))
    item["best_time_to_visit"] = _normalize_text(item.get("best_time_to_visit"))
    item["cluster"] = _normalize_text(item.get("cluster"))
    nearby = item.get("nearby_places")
    item["nearby_places"] = [str(value).strip() for value in nearby if str(value).strip()] if isinstance(nearby, list) else []
    return item


def _time_sort_minutes(value: str) -> int:
    text = _normalize_text(value).upper().replace(".", "")
    match = re.match(r"^(\d{1,2}):(\d{2})\s*([AP]M)$", text)
    if not match:
        return 24 * 60
    hour = int(match.group(1)) % 12
    minute = int(match.group(2))
    if match.group(3) == "PM":
        hour += 12
    return hour * 60 + minute


def _build_sightseeing_pool(destination: str, recommendations: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    base_entries: list[dict[str, Any]] = []
    if isinstance(recommendations, dict):
        base_entries.extend(_normalize_place_entry(entry) for entry in _coerce_place_pool_entries(recommendations.get("attractions"), destination=destination, category="attractions", limit=20))
    if not base_entries:
        base_entries = [_normalize_place_entry(entry) for entry in build_destination_attractions(destination)]

    prompt = f"""
Generate 12 unique tourist attractions for {destination} in JSON only.
Return a JSON object with one key, attractions, containing an array of objects.
Each object must have:
- name
- description
- best_time_to_visit: Morning, Late Morning, Afternoon, or Evening
- cluster: a short grouping label
- nearby_places: 2 to 4 nearby place names

Rules:
1. Do not repeat place names.
2. Include a mix of famous tourist attractions, viewpoints, local/cultural experiences, and evening walkable places.
3. Keep the names realistic and useful for a road trip itinerary.
4. Return only valid JSON.
""".strip()

    try:
        raw = _call_llm_with_timeout(prompt=prompt, temperature=0.35, timeout_seconds=10.0)
        payload = json.loads(_strip_code_fences(raw))
        entries = payload.get("attractions", []) if isinstance(payload, dict) else []
    except Exception:
        entries = []

    if isinstance(recommendations, dict):
        entries.extend(recommendations.get("attractions", []))

    normalized: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if isinstance(entry, str):
            entry = {
                "name": entry,
                "description": f"A notable sightseeing stop in {destination}.",
                "best_time_to_visit": "Morning" if index < 3 else "Afternoon",
                "cluster": "Local Sightseeing",
                "nearby_places": [],
            }
        if isinstance(entry, dict):
            normalized.append(_normalize_place_entry(entry))

    unique = _unique_place_entries([*base_entries, *normalized], set())
    if len(unique) < 12:
        fallback_names = [
            f"{destination} Viewpoint",
            f"{destination} Lake",
            f"{destination} Heritage Walk",
            f"{destination} Botanical Garden",
            f"{destination} Museum",
            f"{destination} Market Walk",
            f"{destination} Temple",
            f"{destination} Forest Stop",
            f"{destination} Tea Estate",
            f"{destination} Scenic Point",
            f"{destination} Cultural Center",
            f"{destination} Garden",
        ]
        for index, name in enumerate(fallback_names):
            if normalize_place_name(name) in {normalize_place_name(item["name"]) for item in unique}:
                continue
            unique.append(
                {
                    "name": name,
                    "description": f"A flexible sightseeing stop in or near {destination}.",
                    "best_time_to_visit": "Morning" if index < 3 else "Afternoon",
                    "cluster": "Fallback",
                    "nearby_places": [],
                }
            )
            if len(unique) >= 12:
                break
    return unique


def _pick_unique_place_by_name(
    entries: list[dict[str, Any]],
    name: str,
    used_places: set[str],
) -> dict[str, Any]:
    target = normalize_place_name(name)
    for entry in entries:
        candidate_name = _normalize_text(entry.get("name"))
        if normalize_place_name(candidate_name) == target and not is_duplicate_place(candidate_name, used_places):
            _reserve_place(entry.get("name", ""), used_places)
            return dict(entry)
    for entry in entries:
        candidate_name = _normalize_text(entry.get("name"))
        if candidate_name and not is_duplicate_place(candidate_name, used_places):
            _reserve_place(candidate_name, used_places)
            return dict(entry)
    fallback = {
        "name": name,
        "description": f"A scenic stop in {name}.",
        "best_time_to_visit": "",
        "cluster": "",
        "nearby_places": [],
    }
    fallback_name = _normalize_text(fallback.get("name")) or "Destination Stop"
    suffix = 2
    while is_duplicate_place(fallback_name, used_places):
        fallback_name = f"{name} {suffix}"
        suffix += 1
    fallback["name"] = fallback_name
    _reserve_place(fallback_name, used_places)
    return fallback


def _pick_sightseeing_place(
    entries: list[dict[str, Any]],
    used_places: set[str],
    *,
    preferred_time: str = "",
    preferred_clusters: list[str] | None = None,
) -> dict[str, Any]:
    preferred_clusters = preferred_clusters or []
    normalized_time = normalize_place_name(preferred_time)
    cluster_keys = {normalize_place_name(value) for value in preferred_clusters if normalize_place_name(value)}

    candidates = [
        entry
        for entry in entries
        if not is_duplicate_place(entry.get("name", ""), used_places)
    ]
    if not candidates:
        return {}

    if normalized_time:
        timed = [entry for entry in candidates if normalize_place_name(entry.get("best_time_to_visit", "")) == normalized_time]
        if timed:
            candidates = timed

    if cluster_keys:
        clustered = [entry for entry in candidates if normalize_place_name(entry.get("cluster", "")) in cluster_keys]
        if clustered:
            candidates = clustered

    chosen = candidates[0]
    _reserve_place(chosen.get("name", ""), used_places)
    return dict(chosen)


def _day_attraction_names(destination: str, day_kind: str, day_index: int) -> list[str]:
    attractions = build_destination_attractions(destination)
    if not attractions:
        return []
    if day_kind == "arrival":
        return [entry.get("name", "") for entry in attractions[:3] if entry.get("name")]
    if day_kind == "return":
        return [entry.get("name", "") for entry in attractions[-3:] if entry.get("name")]
    start = max(0, min(len(attractions) - 4, max(0, day_index - 1)))
    return [entry.get("name", "") for entry in attractions[start : start + 4] if entry.get("name")]


def _build_sightseeing_day_slots(
    *,
    destination: str,
    day_kind: str,
    day_index: int,
    entries: list[dict[str, Any]],
    explorer: dict[str, Any] | None,
    used_places: set[str],
    used_restaurants: set[str],
    used_hotels: set[str],
    meal_place_picker,
    hotel_name: str,
    route_stop: str,
    route_stop_two: str,
    origin: str,
    vehicle_type: str,
    distance_km: float,
    duration_hours: float,
) -> list[dict[str, Any]]:
    selected_attractions: list[dict[str, Any]] = []
    clustered_attractions = _explorer_clustered_attractions(explorer, day_kind, day_index)
    if clustered_attractions:
        for attraction in clustered_attractions:
            name = _normalize_text(attraction.get("name"))
            if not name:
                continue
            normalized = normalize_place_name(name)
            if normalized and normalized in used_places:
                continue
            matched = _pick_unique_place_by_name(entries, name, used_places)
            matched = dict(matched)
            if not _normalize_text(matched.get("name")):
                matched["name"] = name
            if attraction.get("latitude") is not None and matched.get("latitude") in (None, 0, 0.0):
                matched["latitude"] = attraction.get("latitude")
            if attraction.get("longitude") is not None and matched.get("longitude") in (None, 0, 0.0):
                matched["longitude"] = attraction.get("longitude")
            if attraction.get("best_time_to_visit") and not _normalize_text(matched.get("best_time_to_visit")):
                matched["best_time_to_visit"] = attraction.get("best_time_to_visit")
            if attraction.get("nearby_places") and not matched.get("nearby_places"):
                matched["nearby_places"] = attraction.get("nearby_places", [])
            if attraction.get("cluster") and not _normalize_text(matched.get("cluster")):
                matched["cluster"] = attraction.get("cluster")
            selected_attractions.append(matched)
    else:
        attraction_names = _explorer_attraction_names(explorer, day_kind, day_index) or _day_attraction_names(destination, day_kind, day_index)
        if attraction_names:
            for attraction_name in attraction_names:
                selected_attractions.append(_pick_unique_place_by_name(entries, attraction_name, used_places))
        else:
            time_preferences = ["Morning", "Late Morning", "Afternoon", "Evening"]
            if day_kind == "arrival":
                time_preferences = ["Evening", "Evening", "Evening"]
            elif day_kind == "return":
                time_preferences = ["Morning", "Late Morning", "Afternoon", "Afternoon"]
            for preference in time_preferences:
                picked = _pick_sightseeing_place(entries, used_places, preferred_time=preference)
                if picked:
                    selected_attractions.append(picked)

    if day_kind == "arrival" and selected_attractions:
        preferred_order = [
            "Government Botanical Garden",
            "Rose Garden",
            "Ooty Lake",
            "Thread Garden",
            "Charring Cross Evening Walk",
        ]
        preferred_map = {normalize_place_name(name): index for index, name in enumerate(preferred_order)}
        selected_attractions.sort(
            key=lambda item: (
                preferred_map.get(normalize_place_name(item.get("name", "")), len(preferred_order)),
                _best_time_rank(item.get("best_time_to_visit")),
                _normalize_text(item.get("name")),
            )
        )

    if not selected_attractions:
        fallback_names = _explorer_attraction_names(explorer, day_kind, day_index) or _day_attraction_names(destination, day_kind, day_index)
        for attraction_name in fallback_names:
            picked = _pick_unique_place_by_name(entries, attraction_name, used_places)
            if picked:
                selected_attractions.append(picked)
        if not selected_attractions:
            time_preferences = ["Morning", "Late Morning", "Afternoon", "Evening"]
            if day_kind == "arrival":
                time_preferences = ["Evening", "Evening", "Evening"]
            elif day_kind == "return":
                time_preferences = ["Morning", "Late Morning", "Afternoon", "Afternoon"]
            for preference in time_preferences:
                picked = _pick_sightseeing_place(entries, used_places, preferred_time=preference)
                if picked:
                    selected_attractions.append(picked)

    def _pick_meal(category: str, place_destination: str) -> dict[str, Any]:
        picked = meal_place_picker(category, place_destination)
        normalized = normalize_place_name(picked.get("name", ""))
        if category == "restaurants" and normalized:
            used_restaurants.add(normalized)
        if category == "hotels" and normalized:
            used_hotels.add(normalized)
        return picked

    if day_kind == "arrival":
        breakfast_place = _pick_meal("restaurants", origin)
        lunch_place = _pick_meal("restaurants", route_stop_two if route_stop_two else route_stop)
        dinner_place = _pick_meal("restaurants", destination)
        hotel_place = _pick_meal("hotels", destination)
        breakfast_lat, breakfast_lon = _place_lat_lon(breakfast_place)
        lunch_lat, lunch_lon = _place_lat_lon(lunch_place)
        dinner_lat, dinner_lon = _place_lat_lon(dinner_place)
        hotel_lat, hotel_lon = _place_lat_lon(hotel_place)
        return [
            {
                "time": "06:30 AM",
                "type": ActivityCategory.BREAKFAST,
                "title": f"Breakfast at {breakfast_place.get('name', origin)}",
                "place_name": breakfast_place.get("name", origin),
                "location": origin,
                "latitude": breakfast_lat,
                "longitude": breakfast_lon,
                "estimated_duration_minutes": 40,
                "cost_inr": _fallback_slot_cost(ActivityCategory.BREAKFAST, distance_km=distance_km, vehicle_type=vehicle_type, is_travel_day=True, is_return_day=False),
                "reason": "Start the trip with a quick breakfast before leaving the origin city.",
                "best_time_to_visit": "Morning",
                "nearby_places": [],
                "current_location_before": origin,
                "current_location_after": origin,
            },
            {
                "time": "07:15 AM",
                "type": ActivityCategory.DRIVE,
                "title": f"Drive from {origin} toward {destination}",
                "place_name": f"{origin} to {destination}",
                "location": route_stop,
                "estimated_duration_minutes": max(60, int(max(duration_hours, 1.0) * 60 * 0.38)),
                "cost_inr": 0.0,
                "reason": "Cover the first long highway leg while the traveler is still fresh.",
                "best_time_to_visit": "",
                "nearby_places": [],
                "current_location_before": origin,
                "current_location_after": route_stop,
            },
            {
                "time": "10:45 AM",
                "type": ActivityCategory.FUEL,
                "title": f"Fuel and tea stop at {route_stop}",
                "place_name": route_stop,
                "location": route_stop,
                "estimated_duration_minutes": 25,
                "cost_inr": _fallback_slot_cost(ActivityCategory.FUEL, distance_km=distance_km, vehicle_type=vehicle_type, is_travel_day=True, is_return_day=False),
                "reason": "A short route-side pause keeps the drive comfortable and safe.",
                "best_time_to_visit": "Late Morning",
                "nearby_places": [route_stop_two] if route_stop_two else [],
                "current_location_before": route_stop,
                "current_location_after": route_stop,
            },
            {
                "time": "01:00 PM",
                "type": ActivityCategory.LUNCH,
                "title": f"Lunch at {lunch_place.get('name', route_stop_two or route_stop)}",
                "place_name": lunch_place.get("name", route_stop_two or route_stop),
                "location": route_stop_two or route_stop,
                "latitude": lunch_lat,
                "longitude": lunch_lon,
                "estimated_duration_minutes": 50,
                "cost_inr": _fallback_slot_cost(ActivityCategory.LUNCH, distance_km=distance_km, vehicle_type=vehicle_type, is_travel_day=True, is_return_day=False),
                "reason": "Lunch stays on the route so the destination sightseeing can start immediately after arrival.",
                "best_time_to_visit": "Afternoon",
                "nearby_places": [route_stop, route_stop_two] if route_stop_two else [route_stop],
                "current_location_before": route_stop,
                "current_location_after": route_stop,
            },
            {
                "time": "04:15 PM",
                "type": ActivityCategory.HOTEL,
                "title": f"Check in at {hotel_place.get('name', destination)}",
                "place_name": hotel_place.get("name", destination),
                "location": hotel_place.get("name", destination),
                "latitude": hotel_lat,
                "longitude": hotel_lon,
                "estimated_duration_minutes": 35,
                "cost_inr": _fallback_slot_cost(ActivityCategory.HOTEL, distance_km=distance_km, vehicle_type=vehicle_type, is_travel_day=True, is_return_day=False),
                "reason": "Check in once you reach the destination so the evening can be spent sightseeing.",
                "best_time_to_visit": "",
                "nearby_places": [],
                "current_location_before": destination,
                "current_location_after": destination,
            },
        ] + [
            {
                "time": time,
                "type": ActivityCategory.ATTRACTION,
                "title": f"{'Visit' if idx == 0 else 'Explore'} {place.get('name', destination)}",
                "place_name": place.get("name", destination),
                "location": place.get("name", destination),
                "latitude": _place_lat_lon(place)[0],
                "longitude": _place_lat_lon(place)[1],
                "estimated_duration_minutes": 70 if idx == 0 else 60,
                "cost_inr": _fallback_slot_cost(ActivityCategory.ATTRACTION, distance_km=distance_km, vehicle_type=vehicle_type, is_travel_day=True, is_return_day=False),
                "reason": place.get("description", "A scenic destination stop."),
                "best_time_to_visit": place.get("best_time_to_visit", "Evening"),
                "nearby_places": place.get("nearby_places", []),
                "current_location_before": destination,
                "current_location_after": destination,
            }
            for idx, (time, place) in enumerate(
                zip(["05:00 PM", "06:15 PM"], selected_attractions[:2], strict=False)
            )
        ] + [
            {
                "time": "08:30 PM",
                "type": ActivityCategory.DINNER,
                "title": f"Dinner at {dinner_place.get('name', destination)}",
                "place_name": dinner_place.get("name", destination),
                "location": destination,
                "latitude": dinner_lat,
                "longitude": dinner_lon,
                "estimated_duration_minutes": 55,
                "cost_inr": _fallback_slot_cost(ActivityCategory.DINNER, distance_km=distance_km, vehicle_type=vehicle_type, is_travel_day=True, is_return_day=False),
                "reason": "A short dinner keeps the first day relaxed without taking time away from sightseeing.",
                "best_time_to_visit": "Evening",
                "nearby_places": [],
                "current_location_before": destination,
                "current_location_after": destination,
            },
        ]

    if day_kind == "return":
        breakfast_place = _pick_meal("restaurants", destination)
        return_route_stop = route_stop_two or route_stop
        lunch_place = _pick_meal("restaurants", route_stop)
        fuel_place = meal_place_picker("rest_stops", return_route_stop)
        breakfast_lat, breakfast_lon = _place_lat_lon(breakfast_place)
        lunch_lat, lunch_lon = _place_lat_lon(lunch_place)
        fuel_lat, fuel_lon = _place_lat_lon(fuel_place)
        return _annotate_slot_travel_metrics([
            {
                "time": "08:00 AM",
                "type": ActivityCategory.BREAKFAST,
                "title": f"Breakfast at {breakfast_place.get('name', destination)}",
                "place_name": breakfast_place.get("name", destination),
                "location": destination,
                "latitude": breakfast_lat,
                "longitude": breakfast_lon,
                "estimated_duration_minutes": 40,
                "cost_inr": _fallback_slot_cost(ActivityCategory.BREAKFAST, distance_km=distance_km, vehicle_type=vehicle_type, is_travel_day=False, is_return_day=True),
                "reason": "Start the return day with an early meal so the morning sightseeing has enough time.",
                "best_time_to_visit": "Morning",
                "nearby_places": [],
                "current_location_before": destination,
                "current_location_after": destination,
            },
        ] + [
            {
                "time": time,
                "type": ActivityCategory.ATTRACTION,
                "title": f"{'Visit' if idx == 0 else 'Explore'} {place.get('name', destination)}",
                "place_name": place.get("name", destination),
                "location": place.get("name", destination),
                "latitude": _place_lat_lon(place)[0],
                "longitude": _place_lat_lon(place)[1],
                "estimated_duration_minutes": 65 if idx < 2 else 55,
                "cost_inr": _fallback_slot_cost(ActivityCategory.ATTRACTION, distance_km=distance_km, vehicle_type=vehicle_type, is_travel_day=False, is_return_day=True),
                "reason": place.get("description", "A scenic destination stop."),
                "best_time_to_visit": place.get("best_time_to_visit", "Morning"),
                "nearby_places": place.get("nearby_places", []),
                "current_location_before": destination,
                "current_location_after": destination,
            }
            for idx, (time, place) in enumerate(
                zip(["09:00 AM", "10:15 AM", "11:15 AM"], selected_attractions[:3], strict=False)
            )
        ] + [
            {
                "time": "01:15 PM",
                "type": ActivityCategory.LUNCH,
                "title": f"Lunch at {lunch_place.get('name', route_stop)}",
                "place_name": lunch_place.get("name", route_stop),
                "location": lunch_place.get("name", route_stop),
                "latitude": lunch_lat,
                "longitude": lunch_lon,
                "estimated_duration_minutes": 50,
                "cost_inr": _fallback_slot_cost(ActivityCategory.LUNCH, distance_km=distance_km, vehicle_type=vehicle_type, is_travel_day=False, is_return_day=True),
                "reason": "Lunch happens on the route so the return drive stays efficient.",
                "best_time_to_visit": "Afternoon",
                "nearby_places": [return_route_stop] if return_route_stop else [],
                "current_location_before": route_stop,
                "current_location_after": route_stop,
            },
            {
                "time": "02:15 PM",
                "type": ActivityCategory.DRIVE,
                "title": f"Drive back to {origin}",
                "place_name": f"{destination} to {origin}",
                "location": origin,
                "estimated_duration_minutes": max(60, int(max(duration_hours, 1.0) * 60 * 0.55)),
                "cost_inr": 0.0,
                "reason": "Start the return drive after the final destination stops are complete.",
                "best_time_to_visit": "",
                "nearby_places": [],
                "current_location_before": destination,
                "current_location_after": return_route_stop,
            },
            {
                "time": "04:30 PM",
                "type": ActivityCategory.FUEL,
                "title": f"Fuel and tea break at {fuel_place.get('name', return_route_stop)}",
                "place_name": fuel_place.get("name", return_route_stop),
                "location": fuel_place.get("name", return_route_stop),
                "latitude": fuel_lat,
                "longitude": fuel_lon,
                "estimated_duration_minutes": 25,
                "cost_inr": _fallback_slot_cost(ActivityCategory.FUEL, distance_km=distance_km, vehicle_type=vehicle_type, is_travel_day=False, is_return_day=True),
                "reason": "A short fuel break keeps the last stretch relaxed and safe.",
                "best_time_to_visit": "Afternoon",
                "nearby_places": [route_stop] if route_stop else [],
                "current_location_before": route_stop,
                "current_location_after": return_route_stop,
            },
            {
                "time": "07:15 PM",
                "type": ActivityCategory.REST,
                "title": "Arrive back home",
                "place_name": origin,
                "location": origin,
                "estimated_duration_minutes": 30,
                "cost_inr": 0.0,
                "reason": "The trip ends only after the traveler has returned to the origin city.",
                "best_time_to_visit": "",
                "nearby_places": [],
                "current_location_before": route_stop_two or route_stop,
                "current_location_after": origin,
            },
        ])

    breakfast_place = _pick_meal("restaurants", destination)
    lunch_place = _pick_meal("restaurants", destination)
    dinner_place = _pick_meal("restaurants", destination)
    breakfast_lat, breakfast_lon = _place_lat_lon(breakfast_place)
    lunch_lat, lunch_lon = _place_lat_lon(lunch_place)
    dinner_lat, dinner_lon = _place_lat_lon(dinner_place)
    slots = [
        {
            "time": "08:00 AM",
            "type": ActivityCategory.BREAKFAST,
            "title": f"Breakfast at {breakfast_place.get('name', destination)}",
            "place_name": breakfast_place.get("name", destination),
            "location": destination,
            "latitude": breakfast_lat,
            "longitude": breakfast_lon,
            "estimated_duration_minutes": 40,
            "cost_inr": _fallback_slot_cost(ActivityCategory.BREAKFAST, distance_km=distance_km, vehicle_type=vehicle_type, is_travel_day=False, is_return_day=False),
            "reason": "Start the day with a short breakfast before the sightseeing loop begins.",
            "best_time_to_visit": "Morning",
            "nearby_places": [],
            "current_location_before": destination,
            "current_location_after": destination,
        },
    ]
    attraction_times = ["09:00 AM", "10:45 AM", "01:45 PM", "03:45 PM", "05:30 PM"]
    for idx, (time, place) in enumerate(zip(attraction_times, selected_attractions[:5], strict=False)):
        slot_place_lat, slot_place_lon = _place_lat_lon(place)
        slots.append(
            {
                "time": time,
                "type": ActivityCategory.ATTRACTION,
                "title": f"Visit {place.get('name', destination)}",
                "place_name": place.get("name", destination),
                "location": place.get("name", destination),
                "latitude": slot_place_lat,
                "longitude": slot_place_lon,
                "estimated_duration_minutes": 70 if idx < 2 else 60,
                "cost_inr": _fallback_slot_cost(ActivityCategory.ATTRACTION, distance_km=distance_km, vehicle_type=vehicle_type, is_travel_day=False, is_return_day=False),
                "reason": place.get("description", "A scenic destination stop."),
                "best_time_to_visit": place.get("best_time_to_visit", "Morning"),
                "nearby_places": place.get("nearby_places", []),
                "current_location_before": destination,
                "current_location_after": destination,
                "distance_from_previous_km": place.get("distance_from_previous_km"),
                "travel_time_minutes": place.get("travel_time_minutes"),
            }
        )
    slots.extend(
        [
            {
                "time": "12:10 PM",
                "type": ActivityCategory.LUNCH,
                "title": f"Lunch at {lunch_place.get('name', destination)}",
                "place_name": lunch_place.get("name", destination),
                "location": destination,
                "latitude": lunch_lat,
                "longitude": lunch_lon,
                "estimated_duration_minutes": 55,
                "cost_inr": _fallback_slot_cost(ActivityCategory.LUNCH, distance_km=distance_km, vehicle_type=vehicle_type, is_travel_day=False, is_return_day=False),
                "reason": "A short lunch break keeps the destination loop moving without cutting into sightseeing time.",
                "best_time_to_visit": "Afternoon",
                "nearby_places": [],
                "current_location_before": destination,
                "current_location_after": destination,
            },
            {
                "time": "07:30 PM",
                "type": ActivityCategory.DINNER,
                "title": f"Dinner at {dinner_place.get('name', destination)}",
                "place_name": dinner_place.get("name", destination),
                "location": destination,
                "latitude": dinner_lat,
                "longitude": dinner_lon,
                "estimated_duration_minutes": 55,
                "cost_inr": _fallback_slot_cost(ActivityCategory.DINNER, distance_km=distance_km, vehicle_type=vehicle_type, is_travel_day=False, is_return_day=False),
                "reason": "Dinner ends the day after a full sightseeing circuit.",
                "best_time_to_visit": "Evening",
                "nearby_places": [],
                "current_location_before": destination,
                "current_location_after": destination,
            },
        ]
    )
    return _annotate_slot_travel_metrics(slots)


def _build_destination_focused_itinerary(
    *,
    state: TripState,
    origin: str,
    destination: str,
    start_date: datetime,
    trip_days: int,
    budget: float,
    vehicle_type: str,
    number_of_people: int,
    distance_km: float,
    duration_hours: float,
    recommendations: list[dict[str, Any]],
    waypoints: list[str],
) -> FullItinerary:
    rec_map = _recommendation_map(recommendations)
    origin_block = rec_map.get(_location_key(origin))
    destination_block = _destination_explorer_to_block(destination, state.get("destination_explorer")) or rec_map.get(_location_key(destination))
    waypoint_blocks = [rec_map.get(_location_key(item)) for item in waypoints if _location_key(item)]
    route_stop = _route_side_stop_name(origin, destination, waypoints, 0)
    route_stop_two = _route_side_stop_name(origin, destination, waypoints, 1)

    meal_pools = {
        _location_key(origin): _build_destination_place_pool(origin, recommendations=origin_block, allow_llm=False),
        _location_key(route_stop): _build_destination_place_pool(route_stop, recommendations=waypoint_blocks[0] if waypoint_blocks else None, allow_llm=False),
        _location_key(route_stop_two): _build_destination_place_pool(route_stop_two, recommendations=waypoint_blocks[1] if len(waypoint_blocks) > 1 else (waypoint_blocks[0] if waypoint_blocks else None), allow_llm=False),
        _location_key(destination): _build_destination_place_pool(destination, recommendations=destination_block, allow_llm=True),
    }
    token = _set_active_place_pools(meal_pools)
    used_places: set[str] = set()
    used_restaurants: set[str] = set()
    used_hotels: set[str] = set()
    sightseeing_entries = _build_sightseeing_pool(destination, destination_block)

    def meal_place_picker(category: str, place_destination: str) -> dict[str, Any]:
        picked = get_unique_place(category, place_destination, used_places)
        normalized = normalize_place_name(picked.get("name", ""))
        if category == "restaurants" and normalized:
            used_restaurants.add(normalized)
        if category == "hotels" and normalized:
            used_hotels.add(normalized)
        return picked

    travel_tips = [
        "Keep the route-day meals short so the destination sightseeing gets most of the daylight.",
        "Use nearby clusters together: gardens, lakes, viewpoints, and local markets stay more efficient that way.",
        "Start early on the return day so the scenic places fit before lunch and the drive back.",
        "Reserve the hotel only for check-in on arrival day so later days stay attraction-heavy.",
        "Carry water, sunglasses, and a charger for longer scenic loops in the hills.",
    ]

    days: list[DayItinerary] = []
    total_cost = 0.0

    for day_index in range(1, trip_days + 1):
        day_date = start_date + timedelta(days=day_index - 1)
        if day_index == 1:
            day_kind = "arrival"
        elif day_index == trip_days and trip_days >= 3:
            day_kind = "return"
        else:
            day_kind = "full"

        slots = _build_sightseeing_day_slots(
            destination=destination,
            day_kind=day_kind,
            day_index=day_index,
            entries=sightseeing_entries,
            explorer=state.get("destination_explorer"),
            used_places=used_places,
            used_restaurants=used_restaurants,
            used_hotels=used_hotels,
            meal_place_picker=meal_place_picker,
            hotel_name="",
            route_stop=route_stop,
            route_stop_two=route_stop_two,
            origin=origin,
            vehicle_type=vehicle_type,
            distance_km=distance_km,
            duration_hours=duration_hours,
        )

        if day_kind == "arrival":
            day_title = f"Arrival and Sightseeing - {destination}"
            summary = f"Travel from {origin} to {destination}, then spend the evening exploring the town center."
            highlights = [
                "Arrival and hotel check-in",
                "Garden and lake sightseeing",
                "Dinner at a unique local restaurant",
            ]
            day_location = f"{origin} to {destination}"
            distance_today = distance_km
            driving_today = duration_hours
        elif day_kind == "return":
            day_title = f"Return Day - {destination} to {origin}"
            summary = f"Spend the morning on the best scenic loops in {destination} before heading back to {origin}."
            highlights = [
                "Morning scenic circuit",
                "Route-side lunch and fuel stop",
                "Return drive home",
            ]
            day_location = origin
            distance_today = distance_km
            driving_today = duration_hours
        else:
            day_title = f"Destination Exploration - {destination}"
            summary = f"A destination-focused sightseeing day packed with major attractions and a relaxed evening."
            highlights = [
                "Major tourist attractions",
                "Cultural stops and viewpoints",
                "Evening walk and dinner",
            ]
            day_location = destination
            distance_today = 0
            driving_today = 0

        day_total = round(sum(slot["cost_inr"] for slot in slots), 2)
        total_cost += day_total
        day_slots = [
            _make_time_slot(
                time=slot["time"],
                type_=slot["type"],
                title=slot["title"],
                place_name=slot.get("place_name", ""),
                location=slot["location"],
                latitude=slot.get("latitude"),
                longitude=slot.get("longitude"),
                estimated_duration_minutes=slot["estimated_duration_minutes"],
                cost_inr=slot["cost_inr"],
                reason=slot["reason"],
                travel_time_minutes=slot.get("travel_time_minutes"),
                distance_from_previous_km=slot.get("distance_from_previous_km"),
                cluster=_normalize_text(slot.get("cluster")),
                best_time_to_visit=slot.get("best_time_to_visit", ""),
                nearby_places=slot.get("nearby_places", []),
                current_location_before=slot["current_location_before"],
                current_location_after=slot["current_location_after"],
            )
            for slot in slots
        ]
        day_slots = sorted(day_slots, key=lambda slot: _time_sort_minutes(slot.time))

        attraction_cap = 5
        if day_kind == "arrival":
            attraction_cap = 2
        elif day_kind == "return":
            attraction_cap = 3

        capped_slots: list[TimeSlot] = []
        attraction_count = 0
        rest_count = 0
        for slot in day_slots:
            if slot.type == ActivityCategory.REST:
                if rest_count >= 1:
                    continue
                rest_count += 1
            if slot.type in {ActivityCategory.ATTRACTION, ActivityCategory.SIGHTSEEING}:
                if attraction_count >= attraction_cap:
                    continue
                attraction_count += 1
            capped_slots.append(slot)
        day_slots = capped_slots
        day_slots = _apply_location_flow(
            day_slots,
            start_location=origin if day_kind == "arrival" else destination,
            day_kind=day_kind,
            destination=destination,
        )

        days.append(
            DayItinerary(
                day_number=day_index,
                date=day_date.strftime("%d %b %Y"),
                day_title=day_title,
                summary=summary,
                location=day_location,
                time_slots=day_slots,
                day_total_cost_inr=day_total,
                distance_km=distance_today,
                driving_hours=driving_today,
                highlights=highlights,
            )
        )

    # Safety net: if a destination day somehow ends up with fewer than 3 attraction slots,
    # backfill with the next unique scenic place from the pool.
    for day in days:
        if day.day_number == 1 and trip_days > 1:
            continue
        attraction_slots = [slot for slot in day.time_slots if slot.type in {ActivityCategory.ATTRACTION, ActivityCategory.SIGHTSEEING}]
        if len(attraction_slots) >= 3:
            continue
        remaining = [entry for entry in sightseeing_entries if not is_duplicate_place(entry.get("name", ""), used_places)]
        for entry in remaining:
            if len(attraction_slots) >= 3:
                break
            used_places.add(normalize_place_name(entry.get("name", "")))
            day.time_slots.insert(
                max(1, len(day.time_slots) - 2),
                _make_time_slot(
                    time="04:15 PM",
                    type_=ActivityCategory.ATTRACTION,
                    title=f"Visit {entry.get('name', destination)}",
                    place_name=entry.get("name", destination),
                    location=destination,
                    latitude=entry.get("latitude"),
                    longitude=entry.get("longitude"),
                    estimated_duration_minutes=60,
                    cost_inr=_fallback_slot_cost(ActivityCategory.ATTRACTION, distance_km=distance_km, vehicle_type=vehicle_type, is_travel_day=False, is_return_day=day.day_number == trip_days and trip_days >= 3),
                    reason=_normalize_text(entry.get("description"), "A scenic destination stop."),
                    best_time_to_visit=_normalize_text(entry.get("best_time_to_visit")),
                    cluster=_normalize_text(entry.get("cluster")),
                    nearby_places=[str(value).strip() for value in (entry.get("nearby_places") or []) if str(value).strip()],
                    current_location_before=destination,
                    current_location_after=destination,
                    distance_from_previous_km=_safe_float(entry.get("distance_from_previous_km"), 0.0) or None,
                ),
            )
        day.time_slots = _apply_location_flow(
            day.time_slots,
            start_location=origin if day.day_number == 1 else destination,
            day_kind="arrival" if day.day_number == 1 else ("return" if day.day_number == trip_days and trip_days >= 3 else "full"),
            destination=destination,
        )

    # Recompute totals after the safety-net pass so the itinerary header matches
    # the final visible slots.
    normalized_days: list[DayItinerary] = []
    total_cost = 0.0
    for day in days:
        day_total = round(sum(float(slot.cost_inr or 0) for slot in day.time_slots), 2)
        normalized_days.append(day.model_copy(update={"day_total_cost_inr": day_total}))
        total_cost += day_total
    days = normalized_days

    try:
        return FullItinerary(
            trip_id=str(state.get("trip_id", "")),
            origin=origin,
            destination=destination,
            total_days=trip_days,
            start_date=start_date.strftime("%d %b %Y"),
            end_date=(start_date + timedelta(days=trip_days - 1)).strftime("%d %b %Y"),
            days=days,
            total_itinerary_cost_inr=round(total_cost, 2),
            generated_at=datetime.now().strftime("%d %b %Y %I:%M %p"),
            travel_tips=travel_tips,
        )
    finally:
        _reset_active_place_pools(token)


def _run_sightseeing_itinerary_agent(state: dict) -> dict:
    print("=== ITINERARY AGENT START ===")

    origin = _normalize_text(state.get("origin"))
    destination = _normalize_text(state.get("destination"))
    print(f"requested_origin = {origin}")
    print(f"requested_destination = {destination}")
    print(f"normalized_destination = {normalize_place_name(destination)}")
    print(f"destination_used_for_llm = {destination}")
    dates = _normalize_text(state.get("dates"))
    trip_days = max(1, _safe_int(state.get("trip_days"), 1))
    budget = _safe_float(state.get("budget"), 15000.0)
    vehicle = state.get("vehicle", {}) or {}
    vehicle_type = _normalize_text(vehicle.get("vehicle_type"), "car")
    number_of_people = max(1, _safe_int(vehicle.get("number_of_people"), 1))
    route = state.get("route", {}) or {}
    distance_km = _safe_float(route.get("distance_km"), 0.0)
    duration_hours = _safe_float(route.get("duration_hours"), 0.0)
    start_date = _parse_start_date(dates)

    waypoints = state.get("waypoints", []) or []
    if not isinstance(waypoints, list):
        waypoints = [waypoints]
    waypoints = [_normalize_text(item) for item in waypoints if _normalize_text(item)]

    recommendations = state.get("recommendations", []) or []
    rec_blocks = [block for block in recommendations if isinstance(block, dict)]

    itinerary = _build_destination_focused_itinerary(
        state=state,
        origin=origin,
        destination=destination,
        start_date=start_date,
        trip_days=trip_days,
        budget=budget,
        vehicle_type=vehicle_type,
        number_of_people=number_of_people,
        distance_km=distance_km,
        duration_hours=duration_hours,
        recommendations=rec_blocks,
        waypoints=waypoints,
    )
    state["itinerary"] = itinerary.model_dump(mode="json")
    state["travel_tips"] = itinerary.travel_tips
    print(f"final_itinerary_destination = {itinerary.destination}")
    print(f"first_5_selected_places = {[_slot_place_label(slot) for slot in itinerary.days[0].time_slots[:5]] if itinerary.days else []}")
    print("[ITINERARY] Sightseeing-focused complete!")
    return state


run_itinerary_agent = _run_sightseeing_itinerary_agent


async def itinerary_agent(state: TripState) -> TripState:
    return run_itinerary_agent(dict(state))
