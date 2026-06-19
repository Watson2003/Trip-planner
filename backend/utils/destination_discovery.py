from __future__ import annotations

import asyncio
import logging
import math
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from copy import deepcopy
from typing import Any, Iterable, Sequence

from data.destination_fallbacks import (
    DESTINATION_ALIASES,
    DESTINATION_CENTER_COORDS,
    DESTINATION_FALLBACKS,
    DESTINATION_REJECTION_KEYWORDS,
)
from tools.osm_places import classify_osm_place, fetch_osm_places, geocode_location, normalize_place_name as _normalize_place_name
from utils.llm_client import generate_text_with_nvidia_llama, parse_json_payload


logger = logging.getLogger(__name__)

EMPTY_POOLS: dict[str, list[dict[str, Any]]] = {
    "attractions": [],
    "restaurants": [],
    "hotels": [],
    "fuel_stops": [],
    "rest_stops": [],
}

DISCOVERY_TARGETS = {
    "attractions": 10,
    "restaurants": 8,
    "hotels": 5,
}

SUPPORT_TARGETS = {
    "fuel_stops": 5,
    "rest_stops": 4,
}

FAMOUS_ATTRACTION_HINTS = {
    "beach",
    "fort",
    "palace",
    "temple",
    "lake",
    "falls",
    "waterfall",
    "view",
    "viewpoint",
    "peak",
    "garden",
    "museum",
    "park",
    "cliff",
    "heritage",
    "ashram",
    "monastery",
    "market",
    "memorial",
    "church",
    "cathedral",
    "zoo",
    "castle",
    "hill",
    "reserve",
    "sanctuary",
    "mall",
}

ATTRACTION_CLASSIFICATIONS = {
    "must_visit",
    "nature",
    "historical",
    "viewpoint",
    "beach",
    "waterfall",
    "museum",
    "park",
    "shopping",
    "food",
    "hotel",
}


def normalize_place_name(name: str) -> str:
    return _normalize_place_name(name)


def normalize_destination(destination: str) -> str:
    text = normalize_place_name(destination)
    if not text:
        return ""

    for alias in sorted(DESTINATION_ALIASES.keys(), key=len, reverse=True):
        mapped = DESTINATION_ALIASES.get(alias, alias)
        if text == alias:
            return mapped
        if re.search(rf"\b{re.escape(alias)}\b", text):
            return mapped
    return text


def destination_key(destination: str) -> str:
    return normalize_destination(destination)


def _display_destination(destination: str) -> str:
    key = destination_key(destination)
    if not key:
        return ""
    return key.title()


def _destination_center(destination: str) -> tuple[float, float]:
    key = destination_key(destination)
    if key in DESTINATION_CENTER_COORDS:
        return DESTINATION_CENTER_COORDS[key]
    digest = re.sub(r"[^a-z0-9]", "", key)
    if not digest:
        return (20.5937, 78.9629)
    seed = sum(ord(char) for char in digest)
    lat = 20.5937 + ((seed % 500) / 1000.0) - 0.25
    lng = 78.9629 + (((seed // 7) % 500) / 1000.0) - 0.25
    return lat, lng


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _fallback_coordinates(destination: str, index: int = 0) -> tuple[float, float]:
    lat, lng = _destination_center(destination)
    offset = (index % 5) * 0.01
    return lat + offset, lng + offset


def _iter_places(source: Any) -> list[dict[str, Any]]:
    if source is None:
        return []
    if isinstance(source, dict):
        if any(key in source for key in ("name", "latitude", "longitude", "lat", "lng", "tags", "place_id")):
            return [source]
        collected: list[dict[str, Any]] = []
        for value in source.values():
            collected.extend(_iter_places(value))
        return collected
    if isinstance(source, (list, tuple, set)):
        return [item for item in source if isinstance(item, dict)]
    if isinstance(source, dict):
        return [source]
    return []


def _place_text(place: dict[str, Any]) -> str:
    pieces = [
        str(place.get("name") or ""),
        str(place.get("description") or ""),
        str(place.get("address") or ""),
        str(place.get("location") or ""),
    ]
    tags = place.get("tags") if isinstance(place.get("tags"), dict) else {}
    if isinstance(tags, dict):
        pieces.extend(str(tags.get(key) or "") for key in ("tourism", "amenity", "leisure", "natural", "historic", "shop"))
    return " ".join(piece.casefold() for piece in pieces if piece.strip())


def _pool_type(place: dict[str, Any]) -> str:
    category = str(place.get("category") or place.get("type") or "").casefold()
    tags = place.get("tags") if isinstance(place.get("tags"), dict) else {}
    tourism = str(tags.get("tourism") or "").casefold()
    amenity = str(tags.get("amenity") or "").casefold()
    leisure = str(tags.get("leisure") or "").casefold()
    natural = str(tags.get("natural") or "").casefold()
    historic = str(tags.get("historic") or "").casefold()
    shop = str(tags.get("shop") or "").casefold()

    if category in {"hotel", "guest_house", "resort"} or tourism in {"hotel", "guest_house", "resort"} or amenity == "hotel":
        return "hotel"
    if category in {"restaurant", "cafe"} or amenity in {"restaurant", "cafe"}:
        return "restaurant"
    if tourism in {"attraction", "museum", "viewpoint", "gallery", "theme_park"}:
        return "attraction"
    if leisure == "park" or natural in {"peak", "waterfall", "lake", "beach"} or historic or shop == "mall":
        return "attraction"
    return "attraction"


def _attraction_classification(place: dict[str, Any]) -> str:
    pool_type = _pool_type(place)
    if pool_type == "hotel":
        return "hotel"
    if pool_type == "restaurant":
        return "food"

    name = normalize_place_name(place.get("name", ""))
    tags = place.get("tags") if isinstance(place.get("tags"), dict) else {}
    tourism = str(tags.get("tourism") or "").casefold()
    amenity = str(tags.get("amenity") or "").casefold()
    leisure = str(tags.get("leisure") or "").casefold()
    natural = str(tags.get("natural") or "").casefold()
    historic = str(tags.get("historic") or "").casefold()
    shop = str(tags.get("shop") or "").casefold()

    if natural == "beach" or "beach" in name:
        return "beach"
    if natural == "waterfall" or "waterfall" in name or "falls" in name:
        return "waterfall"
    if tourism == "museum" or "museum" in name:
        return "museum"
    if leisure == "park" or "park" in name or "garden" in name:
        return "park"
    if tourism == "viewpoint" or natural == "peak" or "view" in name or "peak" in name or "cliff" in name:
        return "viewpoint"
    if shop == "mall" or "market" in name or "shopping" in name:
        return "shopping"
    if historic or any(term in name for term in ("fort", "palace", "temple", "church", "monastery", "ashram", "heritage", "memorial", "cathedral", "museum")):
        return "historical"
    if tourism in {"theme_park", "gallery"}:
        return "must_visit"
    if tourism == "attraction":
        return "must_visit"
    return "nature"


def _best_time_for(place: dict[str, Any]) -> str:
    classification = str(place.get("classification") or "").casefold()
    pool_type = _pool_type(place)
    if pool_type == "hotel":
        return "Anytime"
    if pool_type == "restaurant":
        return "Breakfast / Lunch / Dinner"
    if classification in {"beach", "waterfall", "viewpoint", "park", "nature"}:
        return "Morning / Evening"
    if classification in {"museum", "historical"}:
        return "Morning"
    if classification == "shopping":
        return "Evening"
    return "Morning"


def _maps_url(name: str, destination: str) -> str:
    query = "+".join(part for part in [name, destination] if part)
    return f"https://www.google.com/maps/search/?api=1&query={query.replace(' ', '+')}"


def _price_range_label(price_level: int, kind: str) -> str:
    labels = ["Budget", "Mid-range", "Premium", "Luxury"]
    index = min(max(int(price_level or 1) - 1, 0), 3)
    if kind == "attraction":
        return "Free" if index == 0 else labels[index]
    return labels[index]


def _hotel_price_level(place: dict[str, Any]) -> int:
    return 2 if int(place.get("source_priority") or 0) >= 2 else 1


def _restaurant_price_level(place: dict[str, Any]) -> int:
    return 1 if int(place.get("source_priority") or 0) >= 2 else 2


def _attraction_price_level(place: dict[str, Any]) -> int:
    classification = str(place.get("classification") or "").casefold()
    return 0 if classification in {"nature", "viewpoint", "beach", "waterfall", "park"} else 1


def _duration_for(place: dict[str, Any]) -> int:
    classification = str(place.get("classification") or "").casefold()
    pool_type = _pool_type(place)
    if pool_type == "restaurant":
        return 60
    if pool_type == "hotel":
        return 30
    if classification == "museum":
        return 90
    if classification == "beach":
        return 120
    if classification == "waterfall":
        return 100
    if classification == "viewpoint":
        return 75
    if classification == "shopping":
        return 90
    if classification == "historical":
        return 80
    if classification == "park":
        return 70
    return 60


def _normalize_entry_place(
    place: dict[str, Any],
    destination: str,
    source: str,
    index: int = 0,
    category_hint: str | None = None,
) -> dict[str, Any]:
    item = dict(place)
    name = str(item.get("name") or item.get("title") or "").strip()
    if not name:
        name = f"{_display_destination(destination)} Place {index + 1}"

    explicit_category = str(item.get("category") or category_hint or "").casefold()
    if explicit_category in {"hotel", "hotels"}:
        pool_type = "hotel"
    elif explicit_category in {"restaurant", "restaurants", "cafe", "food"}:
        pool_type = "restaurant"
    elif explicit_category in {"attraction", "attractions"}:
        pool_type = "attraction"
    else:
        pool_type = _pool_type(item)
    classification = _attraction_classification(item)
    if pool_type != "attraction":
        classification = "food" if pool_type == "restaurant" else "hotel"

    lat = item.get("latitude") or item.get("lat")
    lng = item.get("longitude") or item.get("lng") or item.get("lon")
    try:
        if lat is None or lng is None:
            lat, lng = _fallback_coordinates(destination, index)
        else:
            lat = float(lat)
            lng = float(lng)
    except (TypeError, ValueError):
        lat, lng = _fallback_coordinates(destination, index)

    description = str(item.get("description") or item.get("reason") or "").strip()
    if not description:
        if pool_type == "restaurant":
            description = f"A convenient food stop in {_display_destination(destination)}."
        elif pool_type == "hotel":
            description = f"A practical stay in {_display_destination(destination)}."
        else:
            description = f"A useful sightseeing stop in {_display_destination(destination)}."

    normalized = {
        "name": name,
        "category": pool_type,
        "classification": classification,
        "why_visit": str(item.get("why_visit") or description).strip(),
        "best_time_to_visit": str(item.get("best_time_to_visit") or _best_time_for(item)).strip(),
        "suggested_duration_minutes": int(item.get("suggested_duration_minutes") or item.get("duration_minutes") or _duration_for(item)),
        "latitude": float(lat),
        "longitude": float(lng),
        "address": str(item.get("address") or destination).strip(),
        "description": description,
        "rating": float(item.get("rating") or 0.0),
        "total_reviews": int(item.get("total_reviews") or 0),
        "source": source,
        "discovery_source": str(item.get("discovery_source") or source),
        "place_id": str(item.get("place_id") or "").strip() or f"{source}-{normalize_place_name(name) or index + 1}",
        "fallback_generated": bool(item.get("fallback_generated", False)),
        "tags": item.get("tags") if isinstance(item.get("tags"), dict) else {},
    }

    normalized["distance_from_center_km"] = _distance_from_center(destination, normalized)
    normalized["source_priority"] = int(item.get("source_priority") or _source_priority(source))
    return normalized


def _source_priority(source: str) -> int:
    return {"osm": 3, "llama": 2, "fallback": 1}.get(str(source or "").casefold(), 0)


def _distance_from_center(destination: str, place: dict[str, Any]) -> float:
    try:
        lat = float(place.get("latitude") or 0.0)
        lng = float(place.get("longitude") or 0.0)
    except (TypeError, ValueError):
        return 999.0
    if not lat and not lng:
        return 999.0
    center_lat, center_lng = _destination_center(destination)
    return _haversine_km(center_lat, center_lng, lat, lng)


def _to_hotel_recommendation(destination: str, place: dict[str, Any], index: int) -> dict[str, Any]:
    name = str(place.get("name") or "").strip()
    price_level = _hotel_price_level(place)
    return {
        "place_id": str(place.get("place_id") or f"hotel-{normalize_place_name(name) or index + 1}"),
        "name": name,
        "description": str(place.get("why_visit") or place.get("description") or f"A practical stay in {_display_destination(destination)}.").strip(),
        "address": str(place.get("address") or destination).strip(),
        "rating": float(place.get("rating") or (4.5 if int(place.get("source_priority") or 0) >= 2 else 4.2)),
        "total_reviews": int(place.get("total_reviews") or 120 + (10 * max(0, 4 - index))),
        "price_range": _price_range_label(price_level, "hotel"),
        "price_level": price_level,
        "photo_url": None,
        "lat": float(place.get("latitude") or 0.0),
        "lng": float(place.get("longitude") or 0.0),
        "maps_url": _maps_url(name, destination),
        "website": None,
        "phone": None,
        "open_now": None,
        "category": "Mid-range" if price_level >= 2 else "Budget",
        "estimated_cost_inr": 2500.0 if price_level == 1 else 4000.0 if price_level == 2 else 6500.0 if price_level == 3 else 9000.0,
    }


def _to_restaurant_recommendation(destination: str, place: dict[str, Any], index: int) -> dict[str, Any]:
    name = str(place.get("name") or "").strip()
    price_level = _restaurant_price_level(place)
    cuisine = "Local Cuisine" if int(place.get("source_priority") or 0) >= 2 else "Multi Cuisine"
    return {
        "place_id": str(place.get("place_id") or f"restaurant-{normalize_place_name(name) or index + 1}"),
        "name": name,
        "description": str(place.get("why_visit") or place.get("description") or f"A convenient dining stop in {_display_destination(destination)}.").strip(),
        "address": str(place.get("address") or destination).strip(),
        "rating": float(place.get("rating") or (4.4 if int(place.get("source_priority") or 0) >= 2 else 4.1)),
        "total_reviews": int(place.get("total_reviews") or 90 + (10 * max(0, 7 - index))),
        "price_range": _price_range_label(price_level, "restaurant"),
        "price_level": price_level,
        "photo_url": None,
        "lat": float(place.get("latitude") or 0.0),
        "lng": float(place.get("longitude") or 0.0),
        "maps_url": _maps_url(name, destination),
        "website": None,
        "phone": None,
        "open_now": None,
        "cuisine": cuisine,
        "category": "Both",
        "estimated_cost_inr": 300.0 if price_level == 1 else 600.0 if price_level == 2 else 1000.0 if price_level == 3 else 1500.0,
    }


def _to_attraction_recommendation(destination: str, place: dict[str, Any], index: int) -> dict[str, Any]:
    name = str(place.get("name") or "").strip()
    price_level = _attraction_price_level(place)
    classification = str(place.get("classification") or "must_visit").strip() or "must_visit"
    return {
        "place_id": str(place.get("place_id") or f"attraction-{normalize_place_name(name) or index + 1}"),
        "name": name,
        "description": str(place.get("why_visit") or place.get("description") or f"A scenic stop in {_display_destination(destination)}.").strip(),
        "address": str(place.get("address") or destination).strip(),
        "rating": float(place.get("rating") or (4.6 if int(place.get("source_priority") or 0) >= 2 else 4.2)),
        "total_reviews": int(place.get("total_reviews") or 110 + (8 * max(0, 9 - index))),
        "entry_fee": _price_range_label(price_level, "attraction"),
        "price_level": price_level,
        "photo_url": None,
        "lat": float(place.get("latitude") or 0.0),
        "lng": float(place.get("longitude") or 0.0),
        "maps_url": _maps_url(name, destination),
        "website": None,
        "phone": None,
        "open_now": None,
        "type": classification.replace("_", " ").title(),
        "entry_fee_inr": 0.0 if price_level == 0 else 100.0 if price_level == 1 else 250.0,
    }


def _destination_rejection_terms(destination: str) -> set[str]:
    key = destination_key(destination)
    terms = set(DESTINATION_REJECTION_KEYWORDS.get(key, set()))
    if key:
        terms.add(key)
    return terms


def validate_places_match_destination(destination: str, places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    destination = str(destination or "").strip()
    if not destination:
        return [dict(place) for place in places if isinstance(place, dict)]

    terms = _destination_rejection_terms(destination)
    destination_key_text = destination_key(destination)
    filtered: list[dict[str, Any]] = []
    seen: set[str] = set()

    for place in places:
        if not isinstance(place, dict):
            continue
        name = str(place.get("name") or "").strip()
        if not name:
            continue
        normalized = normalize_place_name(name)
        if not normalized or normalized in seen:
            continue

        haystack = _place_text(place)
        if destination_key_text and destination_key_text not in haystack and any(term in haystack for term in terms):
            continue

        seen.add(normalized)
        filtered.append(dict(place, name=name))

    return filtered


def validate_destination_places(destination: str, places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return validate_places_match_destination(destination, places)


def _flatten_source(source: Any) -> list[dict[str, Any]]:
    return _iter_places(source)


def merge_place_sources(
    osm_places: Any,
    llama_places: Any,
    fallback_places: Any,
) -> list[dict[str, Any]]:
    combined: list[dict[str, Any]] = []
    for source, priority in ((osm_places, "osm"), (llama_places, "llama"), (fallback_places, "fallback")):
        for index, place in enumerate(_flatten_source(source)):
            if not isinstance(place, dict):
                continue
            item = dict(place)
            item.setdefault("discovery_source", priority)
            item.setdefault("source_priority", _source_priority(priority))
            if index == 0:
                item.setdefault("fallback_generated", priority == "fallback")
            combined.append(item)
    return combined


def _merge_preferred(existing: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    fields = ("description", "why_visit", "best_time_to_visit", "address", "rating", "total_reviews", "latitude", "longitude")
    merged = dict(existing)
    for field in fields:
        existing_value = merged.get(field)
        candidate_value = candidate.get(field)
        if existing_value in {None, "", 0, 0.0} and candidate_value not in {None, "", 0, 0.0}:
            merged[field] = candidate_value
    if _source_priority(candidate.get("discovery_source", "")) > _source_priority(merged.get("discovery_source", "")):
        merged["discovery_source"] = candidate.get("discovery_source")
        merged["source"] = candidate.get("source", merged.get("source"))
    merged["fallback_generated"] = bool(merged.get("fallback_generated", False) or candidate.get("fallback_generated", False))
    merged["source_priority"] = max(int(merged.get("source_priority") or 0), int(candidate.get("source_priority") or 0))
    if not merged.get("classification"):
        merged["classification"] = candidate.get("classification")
    if not merged.get("category"):
        merged["category"] = candidate.get("category")
    return merged


def _dedupe_places(places: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    ordered_keys: list[str] = []
    for place in places:
        if not isinstance(place, dict):
            continue
        name = normalize_place_name(place.get("name", ""))
        if not name:
            continue
        key = name
        lat = place.get("latitude") or place.get("lat")
        lng = place.get("longitude") or place.get("lng") or place.get("lon")
        if not key and lat is not None and lng is not None:
            try:
                key = f"{float(lat):.4f}:{float(lng):.4f}"
            except (TypeError, ValueError):
                key = ""
        if not key:
            continue
        if key in seen:
            seen[key] = _merge_preferred(seen[key], place)
        else:
            seen[key] = dict(place)
            ordered_keys.append(key)
    return [seen[key] for key in ordered_keys]


def _category_boost(place: dict[str, Any]) -> float:
    classification = str(place.get("classification") or "").casefold()
    name = normalize_place_name(place.get("name", ""))
    score = 0.0
    if classification in {"must_visit", "historical"}:
        score += 4.5
    elif classification in {"nature", "viewpoint", "beach", "waterfall"}:
        score += 4.0
    elif classification in {"museum", "park"}:
        score += 3.5
    elif classification in {"shopping", "food"}:
        score += 2.5
    if any(term in name for term in FAMOUS_ATTRACTION_HINTS):
        score += 1.0
    return score


def _place_score(place: dict[str, Any], category_counts: Counter[str], preferences: str) -> float:
    name = str(place.get("name") or "").strip()
    if not name:
        return -1000.0

    classification = str(place.get("classification") or "").casefold()
    pool_type = str(place.get("category") or "").casefold()
    score = 0.0

    rating = place.get("rating")
    if isinstance(rating, (int, float)) and rating > 0:
        score += float(rating) * 2.4

    reviews = place.get("total_reviews")
    if isinstance(reviews, (int, float)) and reviews > 0:
        score += min(float(reviews) / 120.0, 4.5)

    distance = float(place.get("distance_from_center_km") or 999.0)
    if distance < 999:
        score += max(0.0, 5.0 - min(distance / 10.0, 5.0))

    score += _category_boost(place)

    if pool_type == "restaurant":
        score += 1.8
    elif pool_type == "hotel":
        score += 1.0

    if preferences:
        haystack = " ".join(
            [
                name.casefold(),
                str(place.get("description") or "").casefold(),
                classification,
                pool_type,
                str(place.get("best_time_to_visit") or "").casefold(),
            ]
        )
        for term in re.split(r"[,\|;/]+", preferences.casefold()):
            term = term.strip()
            if term and term in haystack:
                score += 2.0

    category_frequency = max(1, int(category_counts.get(classification or pool_type or "attraction", 1)))
    score += 1.5 / math.sqrt(category_frequency)

    if place.get("discovery_source") == "osm":
        score += 1.2
    elif place.get("discovery_source") == "llama":
        score += 0.8
    elif place.get("discovery_source") == "fallback":
        score += 0.3

    if len(name) < 4:
        score -= 2.0

    return score


def rank_destination_places(destination: str, places: list[dict[str, Any]], preferences: Any = None) -> list[dict[str, Any]]:
    normalized_preferences = ""
    if isinstance(preferences, str):
        normalized_preferences = preferences
    elif isinstance(preferences, dict):
        normalized_preferences = " ".join(str(value) for value in preferences.values() if str(value).strip())
    elif isinstance(preferences, (list, tuple, set)):
        normalized_preferences = " ".join(str(value) for value in preferences if str(value).strip())

    cleaned = []
    for index, place in enumerate(places):
        if not isinstance(place, dict):
            continue
        item = _normalize_entry_place(place, destination, str(place.get("discovery_source") or place.get("source") or "osm"), index)
        cleaned.append(item)

    counts = Counter(
        str(place.get("classification") or place.get("category") or "attraction").casefold()
        for place in cleaned
    )
    ranked = sorted(
        cleaned,
        key=lambda place: (
            -_place_score(place, counts, normalized_preferences),
            _distance_from_center(destination, place),
            normalize_place_name(place.get("name", "")),
        ),
    )
    return ranked


def _classify_osm_place(place: dict[str, Any]) -> str:
    tags = place.get("tags") if isinstance(place.get("tags"), dict) else {}
    try:
        return classify_osm_place(tags or {})
    except Exception:
        return str(place.get("category") or "attraction")


def _map_osm_place(place: dict[str, Any], destination: str, index: int) -> dict[str, Any]:
    category = _pool_type(place)
    classification = _attraction_classification(place)
    tags = place.get("tags") if isinstance(place.get("tags"), dict) else {}
    name = str(place.get("name") or "").strip()
    description = str(place.get("description") or "").strip()
    if not description:
        description = f"{name} in {_display_destination(destination)}."
    mapped = {
        "name": name,
        "category": category,
        "classification": classification if category == "attraction" else ("food" if category == "restaurant" else "hotel"),
        "why_visit": description,
        "best_time_to_visit": str(place.get("best_time_to_visit") or "").strip() or _best_time_for(place),
        "suggested_duration_minutes": int(place.get("suggested_duration_minutes") or place.get("estimated_duration_minutes") or _duration_for(place)),
        "latitude": float(place.get("latitude") or place.get("lat") or _fallback_coordinates(destination, index)[0]),
        "longitude": float(place.get("longitude") or place.get("lng") or place.get("lon") or _fallback_coordinates(destination, index)[1]),
        "address": str(place.get("address") or destination).strip(),
        "description": description,
        "rating": float(place.get("rating") or 4.2),
        "total_reviews": int(place.get("total_reviews") or 90),
        "source": "osm",
        "discovery_source": "osm",
        "place_id": str(place.get("place_id") or "").strip() or f"osm-{normalize_place_name(name) or index + 1}",
        "fallback_generated": bool(place.get("fallback_generated", False)),
        "tags": tags if isinstance(tags, dict) else {},
    }
    mapped["distance_from_center_km"] = _distance_from_center(destination, mapped)
    mapped["source_priority"] = _source_priority("osm")
    return mapped


def _parse_llama_payload(destination: str, raw_text: str, expected_count: int = 0) -> list[dict[str, Any]]:
    try:
        payload = parse_json_payload(raw_text)
    except Exception:
        return []

    if isinstance(payload, dict):
        entries = payload.get("places") or payload.get("items") or payload.get("attractions") or payload.get("restaurants") or payload.get("hotels") or []
        if isinstance(entries, dict):
            flattened: list[dict[str, Any]] = []
            for value in entries.values():
                flattened.extend(_iter_places(value))
            entries = flattened
    elif isinstance(payload, list):
        entries = payload
    else:
        entries = []

    if not isinstance(entries, list):
        return []

    normalized: list[dict[str, Any]] = []
    for index, entry in enumerate(entries[: expected_count or len(entries)]):
        if isinstance(entry, str):
            normalized.append(
                {
                    "name": entry.strip(),
                    "why_visit": f"Recommended place in {_display_destination(destination)}.",
                    "best_time_to_visit": "Morning",
                    "suggested_duration_minutes": 75,
                }
            )
        elif isinstance(entry, dict):
            normalized.append(dict(entry))
    return normalized


def _llama_prompt(destination: str, candidates: list[dict[str, Any]], preferences: Any = None, count_hint: int = 0) -> str:
    candidate_payload = [
        {
            "name": place.get("name"),
            "category": place.get("category"),
            "classification": place.get("classification"),
            "why_visit": place.get("why_visit") or place.get("description"),
            "best_time_to_visit": place.get("best_time_to_visit"),
        }
        for place in candidates[:40]
    ]
    prefs = ""
    if isinstance(preferences, str):
        prefs = preferences
    elif isinstance(preferences, dict):
        prefs = " ".join(str(value) for value in preferences.values() if str(value).strip())
    elif isinstance(preferences, (list, tuple, set)):
        prefs = " ".join(str(value) for value in preferences if str(value).strip())

    return f"""
You are improving road-trip destination discovery for {destination}.
Return valid JSON only.

Destination: {destination}
Preferences: {prefs or "none"}
Candidate places JSON:
{candidate_payload}

Return this shape:
{{
  "attractions": [
    {{
      "name": "string",
      "classification": "must_visit|nature|historical|viewpoint|beach|waterfall|museum|park|shopping",
      "why_visit": "string",
      "best_time_to_visit": "string",
      "duration_minutes": 60
    }}
  ],
  "restaurants": [
    {{
      "name": "string",
      "why_visit": "string",
      "best_time_to_visit": "Breakfast / Lunch / Dinner",
      "duration_minutes": 45
    }}
  ],
  "hotels": [
    {{
      "name": "string",
      "why_visit": "string",
      "best_time_to_visit": "Anytime",
      "duration_minutes": 30
    }}
  ]
}}

Rules:
1. Only return places that belong to {destination}.
2. Remove weak, generic, or duplicate places.
3. Add missing famous places if the candidate list is thin.
4. Prefer destination-specific attractions, viewpoints, lakes, beaches, waterfalls, museums, parks, historical sites, markets, restaurants, and hotels.
5. Do not mention any destination other than {destination}.
6. Return JSON only, no markdown.
7. Aim for at least {max(count_hint, DISCOVERY_TARGETS["attractions"])} attractions, {DISCOVERY_TARGETS["restaurants"]} restaurants, and {DISCOVERY_TARGETS["hotels"]} hotels when possible.
""".strip()


def _llama_generate_catalog(destination: str, candidates: list[dict[str, Any]], preferences: Any = None) -> dict[str, list[dict[str, Any]]]:
    prompt = _llama_prompt(destination, candidates, preferences=preferences, count_hint=len(candidates))
    try:
        raw = _call_llama_with_timeout(prompt, temperature=0.2, timeout_seconds=4.5)
    except Exception as exc:
        logger.warning("Llama discovery failed for %s: %s", destination, exc)
        return {"attractions": [], "restaurants": [], "hotels": []}

    if not raw:
        return {"attractions": [], "restaurants": [], "hotels": []}

    try:
        payload = parse_json_payload(raw)
    except Exception:
        payload = {}

    if not isinstance(payload, dict):
        return {"attractions": [], "restaurants": [], "hotels": []}

    catalog: dict[str, list[dict[str, Any]]] = {"attractions": [], "restaurants": [], "hotels": []}
    for key in catalog:
        entries = payload.get(key, [])
        if not isinstance(entries, list):
            continue
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            pool_type = "restaurant" if key == "restaurants" else "hotel" if key == "hotels" else "attraction"
            classification = str(entry.get("classification") or "").strip().casefold()
            if pool_type == "attraction" and classification not in ATTRACTION_CLASSIFICATIONS:
                classification = "must_visit"
            if pool_type == "restaurant":
                classification = "food"
            if pool_type == "hotel":
                classification = "hotel"
            catalog[key].append(
                {
                    "name": name,
                    "category": pool_type,
                    "classification": classification,
                    "why_visit": str(entry.get("why_visit") or entry.get("description") or "").strip(),
                    "best_time_to_visit": str(entry.get("best_time_to_visit") or "").strip(),
                    "suggested_duration_minutes": int(entry.get("duration_minutes") or entry.get("suggested_duration_minutes") or (60 if pool_type == "attraction" else 45 if pool_type == "restaurant" else 30)),
                    "address": destination,
                    "source": "llama",
                    "discovery_source": "llama",
                    "fallback_generated": True,
                    "latitude": float(entry.get("latitude") or 0.0),
                    "longitude": float(entry.get("longitude") or 0.0),
                }
            )
    return catalog


def _fallback_catalog(destination: str) -> dict[str, list[dict[str, Any]]]:
    key = destination_key(destination)
    return deepcopy(DESTINATION_FALLBACKS.get(key, EMPTY_POOLS))


def _generate_support_places(destination: str, kind: str, count: int) -> list[dict[str, Any]]:
    label = _display_destination(destination)
    items: list[dict[str, Any]] = []
    for index in range(count):
        if kind == "hotels":
            items.append(
                {
                    "name": f"{label} Central Stay {index + 1}",
                    "description": f"Practical stay in {label}.",
                    "category": "hotel",
                    "classification": "hotel",
                    "best_time_to_visit": "Anytime",
                    "suggested_duration_minutes": 30,
                    "address": destination,
                    "fallback_generated": True,
                    "source": "fallback",
                    "discovery_source": "fallback",
                }
            )
        elif kind == "restaurants":
            items.append(
                {
                    "name": f"{label} Food Stop {index + 1}",
                    "description": f"Convenient meal stop in {label}.",
                    "category": "restaurant",
                    "classification": "food",
                    "best_time_to_visit": "Breakfast / Lunch / Dinner",
                    "suggested_duration_minutes": 45,
                    "address": destination,
                    "fallback_generated": True,
                    "source": "fallback",
                    "discovery_source": "fallback",
                }
            )
        else:
            items.append(
                {
                    "name": f"{label} Scenic Stop {index + 1}",
                    "description": f"Useful sightseeing stop in {label}.",
                    "category": "attraction",
                    "classification": "must_visit",
                    "best_time_to_visit": "Morning / Evening",
                    "suggested_duration_minutes": 60,
                    "address": destination,
                    "fallback_generated": True,
                    "source": "fallback",
                    "discovery_source": "fallback",
                }
            )
    return items


def _bucket_places(places: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets = {"attractions": [], "restaurants": [], "hotels": []}
    for place in places:
        pool_type = str(place.get("category") or "").casefold()
        if pool_type == "restaurant":
            buckets["restaurants"].append(place)
        elif pool_type == "hotel":
            buckets["hotels"].append(place)
        else:
            buckets["attractions"].append(place)
    return buckets


def _call_llama_with_timeout(prompt: str, *, temperature: float, timeout_seconds: float) -> str:
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(generate_text_with_nvidia_llama, prompt, temperature)
        try:
            return future.result(timeout=timeout_seconds)
        except FuturesTimeoutError:
            logger.warning("Llama request timed out after %.1fs", timeout_seconds)
            return ""


def _ensure_minimums(
    destination: str,
    ranked_places: list[dict[str, Any]],
    fallback_places: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    buckets = _bucket_places(ranked_places)
    for key, target in DISCOVERY_TARGETS.items():
        if len(buckets[key]) >= target:
            continue
        source_pool = list(fallback_places.get(key, []))
        if len(source_pool) < (target - len(buckets[key])):
            source_pool.extend(_generate_support_places(destination, key, target - len(buckets[key]) - len(source_pool)))
        for item in source_pool:
            if len(buckets[key]) >= target:
                break
            buckets[key].append(item)
    for key in buckets:
        buckets[key] = rank_destination_places(destination, validate_places_match_destination(destination, buckets[key]))
        if len(buckets[key]) < DISCOVERY_TARGETS.get(key, 0):
            needed = DISCOVERY_TARGETS[key] - len(buckets[key])
            buckets[key].extend(_generate_support_places(destination, key, needed))
            buckets[key] = rank_destination_places(destination, validate_places_match_destination(destination, buckets[key]))
    return buckets


async def discover_destination_place_catalog(
    destination: str,
    preferences: Any = None,
    *,
    include_llm: bool = True,
) -> dict[str, Any]:
    raw_destination = str(destination or "").strip()
    normalized_destination = normalize_destination(raw_destination)
    display_destination = _display_destination(raw_destination or normalized_destination)
    if not raw_destination:
        return {
            "destination": "",
            "normalized_destination": "",
            "osm_count": 0,
            "llama_count": 0,
            "fallback_count": 0,
            "final_attractions_count": 0,
            "final_restaurants_count": 0,
            "final_hotels_count": 0,
            "final_attractions": [],
            "final_restaurants": [],
            "final_hotels": [],
            "fallback_generated": False,
        }

    try:
        osm_places_raw = await asyncio.wait_for(fetch_osm_places(raw_destination, radius_km=15), timeout=8.0)
    except Exception as exc:
        logger.warning("OSM discovery failed for %s: %s", raw_destination, exc)
        osm_places_raw = []

    osm_places = validate_places_match_destination(raw_destination, _flatten_source(osm_places_raw))
    osm_places = [_map_osm_place(place, raw_destination, index) for index, place in enumerate(osm_places)]

    llama_places: dict[str, list[dict[str, Any]]] = {"attractions": [], "restaurants": [], "hotels": []}
    if include_llm:
        osm_attractions = sum(1 for place in osm_places if str(place.get("category") or "").casefold() == "attraction")
        if osm_attractions < 8 or not osm_places:
            llama_places = _llama_generate_catalog(raw_destination, osm_places, preferences=preferences)

    fallback_places = _fallback_catalog(raw_destination)
    fallback_standardized: dict[str, list[dict[str, Any]]] = {
        "attractions": [
            _normalize_entry_place(place, raw_destination, "fallback", index, category_hint="attraction")
            for index, place in enumerate(fallback_places.get("attractions", []))
        ],
        "restaurants": [
            _normalize_entry_place(place, raw_destination, "fallback", index, category_hint="restaurant")
            for index, place in enumerate(fallback_places.get("restaurants", []))
        ],
        "hotels": [
            _normalize_entry_place(place, raw_destination, "fallback", index, category_hint="hotel")
            for index, place in enumerate(fallback_places.get("hotels", []))
        ],
    }

    merged = merge_place_sources(osm_places, llama_places, fallback_standardized)
    merged = validate_places_match_destination(raw_destination, merged)
    ranked = rank_destination_places(raw_destination, merged, preferences)

    buckets = _ensure_minimums(raw_destination, ranked, fallback_standardized)

    support_fuel = fallback_places.get("fuel_stops", [])
    support_rest = fallback_places.get("rest_stops", [])
    if not support_fuel:
        support_fuel = _generate_support_places(raw_destination, "fuel_stops", SUPPORT_TARGETS["fuel_stops"])
    if not support_rest:
        support_rest = _generate_support_places(raw_destination, "rest_stops", SUPPORT_TARGETS["rest_stops"])

    final_catalog = {
        "destination": display_destination or raw_destination,
        "normalized_destination": normalized_destination,
        "osm_count": len(osm_places),
        "llama_count": sum(len(items) for items in llama_places.values()),
        "fallback_count": sum(len(items) for items in fallback_standardized.values()),
        "final_attractions_count": len(buckets["attractions"]),
        "final_restaurants_count": len(buckets["restaurants"]),
        "final_hotels_count": len(buckets["hotels"]),
        "final_attractions": buckets["attractions"],
        "final_restaurants": buckets["restaurants"],
        "final_hotels": buckets["hotels"],
        "attractions": buckets["attractions"],
        "restaurants": buckets["restaurants"],
        "hotels": buckets["hotels"],
        "fuel_stops": validate_places_match_destination(raw_destination, [_normalize_entry_place(item, raw_destination, "fallback", index, category_hint="attraction") for index, item in enumerate(support_fuel)]),
        "rest_stops": validate_places_match_destination(raw_destination, [_normalize_entry_place(item, raw_destination, "fallback", index, category_hint="attraction") for index, item in enumerate(support_rest)]),
        "fallback_generated": bool(llama_places["attractions"] or llama_places["restaurants"] or llama_places["hotels"] or fallback_standardized),
    }
    return final_catalog


async def discover_destination_places(
    destination: str,
    preferences: Any = None,
    *,
    include_llm: bool = True,
) -> dict[str, Any]:
    return await discover_destination_place_catalog(destination, preferences, include_llm=include_llm)


def discovery_catalog_to_recommendation_catalog(catalog: dict[str, Any], destination: str) -> dict[str, Any]:
    hotels = [
        _to_hotel_recommendation(destination, place, index)
        for index, place in enumerate(_iter_places(catalog.get("hotels", [])))
    ]
    restaurants = [
        _to_restaurant_recommendation(destination, place, index)
        for index, place in enumerate(_iter_places(catalog.get("restaurants", [])))
    ]
    attractions = [
        _to_attraction_recommendation(destination, place, index)
        for index, place in enumerate(_iter_places(catalog.get("attractions", [])))
    ]
    return {
        "destination": _display_destination(destination) or str(destination).strip(),
        "hotels": hotels,
        "restaurants": restaurants,
        "attractions": attractions,
        "fallback_generated": bool(catalog.get("fallback_generated", False)),
    }


def _run_async_sync(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coro).result()


def generate_destination_places_with_llama(destination: str, category: str, count: int) -> list[dict[str, Any]]:
    destination = str(destination or "").strip()
    category = str(category or "").strip().lower()
    count = max(0, int(count))
    if not destination or not category or count <= 0:
        return []

    prompt = f"""
Generate destination-specific places for {destination}.
Category: {category}
Count: {count}

Return valid JSON only in this shape:
[
  {{
    "name": "string",
    "why_visit": "string",
    "best_time_to_visit": "string",
    "duration_minutes": 60
  }}
]

Rules:
1. Only use places that truly belong to {destination}.
2. Do not include cross-city places.
3. Prefer famous and useful places for road trips.
4. Return JSON only, no markdown.
""".strip()

    try:
        raw = _call_llama_with_timeout(prompt, temperature=0.25, timeout_seconds=4.5)
    except Exception as exc:
        logger.warning("Llama generation failed for %s: %s", destination, exc)
        return []

    if not raw:
        return []

    try:
        payload = parse_json_payload(raw)
    except Exception:
        return []

    if not isinstance(payload, list):
        return []

    normalized: list[dict[str, Any]] = []
    for index, entry in enumerate(payload[:count]):
        if isinstance(entry, str):
            normalized.append(
                    _normalize_entry_place(
                        {
                            "name": entry,
                            "why_visit": f"Suggested place in {_display_destination(destination)}.",
                            "best_time_to_visit": "Morning",
                            "suggested_duration_minutes": 60,
                        },
                        destination,
                        "llama",
                        index,
                        category_hint=category,
                    )
                )
        elif isinstance(entry, dict):
            normalized.append(_normalize_entry_place(entry, destination, "llama", index, category_hint=category))
    return validate_places_match_destination(destination, normalized)[:count]


def build_destination_place_pools(destination: str, *, include_llm: bool = True) -> dict[str, list[dict[str, Any]]]:
    catalog = _run_async_sync(discover_destination_place_catalog(destination, include_llm=include_llm))
    return {
        "attractions": list(catalog.get("attractions", [])),
        "restaurants": list(catalog.get("restaurants", [])),
        "hotels": list(catalog.get("hotels", [])),
        "fuel_stops": list(catalog.get("fuel_stops", [])),
        "rest_stops": list(catalog.get("rest_stops", [])),
    }


def build_destination_attractions(destination: str) -> list[dict[str, Any]]:
    return build_destination_place_pools(destination, include_llm=True).get("attractions", [])
