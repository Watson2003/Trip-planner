from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Iterable
from typing import Any

from agents.state import TripState
from tools.osm_places import normalize_place_name
from utils.destination_places import build_destination_place_pools, generate_destination_places_with_llama, validate_destination_places
from utils.llm import call_llm_json


logger = logging.getLogger(__name__)


def _normalize_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _place_key(place: dict[str, Any]) -> str:
    name = _normalize_text(place.get("name"))
    if name:
        return normalize_place_name(name)
    lat = place.get("latitude") or place.get("lat")
    lon = place.get("longitude") or place.get("lng") or place.get("lon")
    try:
        if lat is not None and lon is not None:
            return f"{float(lat):.4f}:{float(lon):.4f}"
    except (TypeError, ValueError):
        pass
    return ""


def _place_category(place: dict[str, Any]) -> str:
    category = _normalize_text(place.get("category")).casefold()
    tags = place.get("tags") if isinstance(place.get("tags"), dict) else {}
    tourism = _normalize_text(tags.get("tourism")).casefold()
    amenity = _normalize_text(tags.get("amenity")).casefold()
    natural = _normalize_text(tags.get("natural")).casefold()
    historic = _normalize_text(tags.get("historic")).casefold()
    leisure = _normalize_text(tags.get("leisure")).casefold()

    if category:
        return category
    if tourism:
        return tourism
    if amenity:
        return amenity
    if natural:
        return natural
    if historic:
        return "historic"
    if leisure:
        return leisure
    return "attraction"


def _best_time_hint(place: dict[str, Any]) -> str:
    value = _normalize_text(place.get("best_time_to_visit")).casefold()
    if value:
        return value
    category = _place_category(place)
    if category in {"restaurant", "cafe"}:
        return "Breakfast / Lunch / Dinner"
    if category in {"hotel", "guest_house", "resort"}:
        return "Anytime"
    if category in {"museum", "historic"}:
        return "Morning"
    if category in {"viewpoint", "peak", "waterfall", "lake", "park", "attraction"}:
        return "Morning / Evening"
    return "Morning"


def _duration_hint(place: dict[str, Any]) -> int:
    value = place.get("suggested_duration_minutes") or place.get("estimated_duration_minutes")
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    category = _place_category(place)
    if category in {"restaurant", "cafe"}:
        return 45
    if category in {"hotel", "guest_house", "resort"}:
        return 30
    if category in {"museum", "historic"}:
        return 75
    if category in {"viewpoint", "peak"}:
        return 90
    if category in {"waterfall", "lake", "park", "attraction"}:
        return 100
    return 60


def _quality_score(place: dict[str, Any]) -> float:
    score = 0.0
    name = _normalize_text(place.get("name"))
    if not name:
        return -100.0

    category = _place_category(place)
    rating = place.get("rating")
    reviews = place.get("total_reviews") or place.get("review_count")
    if isinstance(rating, (int, float)):
        score += float(rating) * 2.0
    if isinstance(reviews, (int, float)):
        score += min(float(reviews) / 100.0, 4.0)
    if category in {"museum", "viewpoint", "attraction"}:
        score += 4.0
    if category in {"park", "peak", "waterfall", "lake", "historic"}:
        score += 4.5
    if category in {"restaurant", "cafe"}:
        score += 2.8
    if category in {"hotel", "guest_house", "resort"}:
        score += 2.2
    if any(term in normalize_place_name(name) for term in ("hotel", "restaurant")) and category not in {"hotel", "restaurant", "cafe"}:
        score -= 1.0
    if len(name) < 3:
        score -= 3.0
    if re.fullmatch(r"[a-z0-9\s-]+", normalize_place_name(name) or "") is None:
        score += 0.1
    return score


def _group_key(place: dict[str, Any]) -> str:
    lat = place.get("latitude") or place.get("lat")
    lon = place.get("longitude") or place.get("lng") or place.get("lon")
    try:
        return f"{round(float(lat), 2):.2f}:{round(float(lon), 2):.2f}"
    except (TypeError, ValueError):
        return "unknown"


def _extract_destination_places(state: TripState, osm_places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    destination = normalize_place_name(state.get("destination", ""))
    if destination:
        destination_places = [
            place
            for place in osm_places
            if destination in normalize_place_name(place.get("name", ""))
            or destination in normalize_place_name(place.get("address", ""))
            or destination in normalize_place_name(place.get("location", ""))
        ]
        if destination_places:
            return destination_places

    recommendations = state.get("recommendations", []) or []
    if isinstance(recommendations, list):
        for block in recommendations:
            if not isinstance(block, dict):
                continue
            if destination and destination != normalize_place_name(block.get("location", "")):
                continue
            extracted: list[dict[str, Any]] = []
            for category in ("hotels", "restaurants", "attractions"):
                items = block.get(category, []) or []
                if isinstance(items, list):
                    extracted.extend(item for item in items if isinstance(item, dict))
            if extracted:
                return extracted
    return osm_places


def _dedupe_places(places: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for place in places:
        if not isinstance(place, dict):
            continue
        name = _normalize_text(place.get("name"))
        key = _place_key(place) or normalize_place_name(name)
        if not name or not key or key in seen:
            continue
        if _quality_score(place) < -2.0:
            continue
        seen.add(key)
        cleaned.append(place)
    return cleaned


def _classify_buckets(places: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets = {
        "top_attractions": [],
        "hidden_gems": [],
        "restaurants": [],
        "hotels": [],
        "evening_places": [],
        "rainy_day_places": [],
        "scenic_places": [],
    }

    for place in sorted(places, key=_quality_score, reverse=True):
        category = _place_category(place)
        payload = {
            "name": _normalize_text(place.get("name")),
            "category": category,
            "reason": _normalize_text(place.get("reason")) or _normalize_text(place.get("description")) or "Good destination fit.",
            "best_time_to_visit": _best_time_hint(place),
            "suggested_duration_minutes": _duration_hint(place),
            "latitude": float(place.get("latitude") or place.get("lat") or 0.0),
            "longitude": float(place.get("longitude") or place.get("lng") or place.get("lon") or 0.0),
            "fallback_generated": bool(place.get("fallback_generated", False)),
        }

        if category in {"restaurant", "cafe"}:
            buckets["restaurants"].append(payload)
            if "evening" in payload["best_time_to_visit"].casefold():
                buckets["evening_places"].append(payload)
        elif category in {"hotel", "guest_house", "resort"}:
            buckets["hotels"].append(payload)
        else:
            buckets["top_attractions"].append(payload)
            if category in {"viewpoint", "peak", "lake", "park"}:
                buckets["scenic_places"].append(payload)
            if category in {"museum", "historic", "attraction"}:
                buckets["hidden_gems"].append(payload)
            if category in {"museum", "historic", "attraction"} or "rain" in payload["reason"].casefold():
                buckets["rainy_day_places"].append(payload)
            if "evening" in payload["best_time_to_visit"].casefold() or category in {"lake", "park", "viewpoint"}:
                buckets["evening_places"].append(payload)

    for key in buckets:
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for place in buckets[key]:
            place_key = normalize_place_name(place.get("name", ""))
            if not place_key or place_key in seen:
                continue
            seen.add(place_key)
            deduped.append(place)
        buckets[key] = deduped

    return buckets


def _summarize_weather(weather_data: Any) -> str:
    if isinstance(weather_data, dict):
        weather_data = [weather_data]
    if not isinstance(weather_data, list) or not weather_data:
        return "Weather data unavailable."
    parts: list[str] = []
    for entry in weather_data[:4]:
        if not isinstance(entry, dict):
            continue
        label = _normalize_text(entry.get("summary") or entry.get("description") or entry.get("condition"))
        rain = _normalize_text(entry.get("rain") or entry.get("precipitation"))
        temp = _normalize_text(entry.get("temp") or entry.get("temperature"))
        piece = ", ".join(part for part in [label, temp, rain] if part)
        if piece:
            parts.append(piece)
    return "; ".join(parts) if parts else "Weather data unavailable."


def _summarize_preferences(user_preferences: Any) -> str:
    prefs = [str(item).strip() for item in _as_list(user_preferences) if str(item).strip()]
    return ", ".join(prefs) if prefs else "No specific preferences."


def _serialize_candidates(places: list[dict[str, Any]], limit: int = 60) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for place in sorted(places, key=_quality_score, reverse=True)[:limit]:
        candidates.append(
            {
                "name": _normalize_text(place.get("name")),
                "category": _place_category(place),
                "rating": place.get("rating"),
                "reviews": place.get("total_reviews") or place.get("review_count"),
                "best_time_to_visit": _best_time_hint(place),
                "latitude": float(place.get("latitude") or place.get("lat") or 0.0),
                "longitude": float(place.get("longitude") or place.get("lng") or place.get("lon") or 0.0),
                "reason": _normalize_text(place.get("description")) or _normalize_text(place.get("reason")),
                "group": _group_key(place),
            }
        )
    return candidates


def _strip_code_fences(text: str) -> str:
    cleaned = _normalize_text(text)
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


async def _call_nvidia_json(prompt: str, temperature: float = 0.2, timeout_seconds: float = 5.0) -> str:
    try:
        return await asyncio.wait_for(asyncio.to_thread(call_llm_json, prompt, temperature), timeout=timeout_seconds)
    except Exception as exc:
        logger.warning("NVIDIA LLM ranking failed: %s", exc)
        return ""


def _build_prompt(
    *,
    destination: str,
    trip_days: int,
    user_preferences: str,
    weather_summary: str,
    candidate_places: list[dict[str, Any]],
) -> str:
    return f"""
You are a travel place ranking assistant for a road trip itinerary.

Destination: {destination}
Trip days: {trip_days}
User preferences: {user_preferences}
Weather summary: {weather_summary}

Rank the best places using:
- popularity
- tourist value
- uniqueness
- distance grouping
- weather suitability
- family/couple/friends suitability
- morning / afternoon / evening suitability

Return JSON only in this exact shape:
{{
  "top_attractions": [{{"name":"", "category":"", "reason":"", "best_time_to_visit":"", "suggested_duration_minutes": 0, "latitude": 0, "longitude": 0, "fallback_generated": false}}],
  "hidden_gems": [],
  "restaurants": [],
  "hotels": [],
  "evening_places": [],
  "rainy_day_places": [],
  "scenic_places": []
}}

Rules:
1. Remove duplicates and low-quality places.
2. Prefer real tourist places over generic business names.
3. Group nearby places together so the itinerary is efficient.
4. If the input list is too small for any category, generate missing places and set fallback_generated to true.
5. Use only the places below unless you must generate a fallback place.

Candidate places:
{json.dumps(candidate_places, ensure_ascii=False, indent=2)}
""".strip()


def _parse_ranked_payload(payload_text: str) -> dict[str, Any]:
    try:
        data = json.loads(_strip_code_fences(payload_text))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _normalize_output_places(items: Any, *, category: str) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        name = _normalize_text(item.get("name"))
        key = normalize_place_name(name)
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "name": name,
                "category": _normalize_text(item.get("category"), category),
                "reason": _normalize_text(item.get("reason"), "Good destination fit."),
                "best_time_to_visit": _normalize_text(item.get("best_time_to_visit"), "Morning"),
                "suggested_duration_minutes": int(item.get("suggested_duration_minutes") or 60),
                "latitude": float(item.get("latitude") or 0.0),
                "longitude": float(item.get("longitude") or 0.0),
                "fallback_generated": bool(item.get("fallback_generated", False)),
            }
        )
    return normalized


def _generate_fallback_places(
    destination: str,
    *,
    category: str,
    needed: int,
    fallback_generated: bool = True,
    seed_catalog: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    pools = seed_catalog or build_destination_place_pools(destination, include_llm=False)
    source_category = "attractions"
    if category == "restaurants":
        source_category = "restaurants"
    elif category == "hotels":
        source_category = "hotels"

    source_items = list(pools.get(source_category, []))
    if len(source_items) < needed:
        source_items.extend(generate_destination_places_with_llama(destination, source_category, needed - len(source_items)))

    generated: list[dict[str, Any]] = []
    for index, item in enumerate(source_items[:needed]):
        name = _normalize_text(item.get("name"))
        if not name:
            continue
        generated.append(
            {
                "name": name,
                "category": category,
                "reason": _normalize_text(item.get("description")) or f"Fallback-generated {category.replace('_', ' ')} for {destination}.",
                "best_time_to_visit": "Morning" if category in {"top_attractions", "hidden_gems", "scenic_places"} else "Evening" if category == "evening_places" else "Anytime",
                "suggested_duration_minutes": 60 if category not in {"hotels"} else 30,
                "latitude": 0.0,
                "longitude": 0.0,
                "fallback_generated": fallback_generated,
            }
        )
    return validate_destination_places(destination, generated)


async def destination_explorer_agent(state: TripState) -> TripState:
    destination = _normalize_text(state.get("destination"))
    trip_days = max(1, int(state.get("trip_days") or 1))
    user_preferences = _summarize_preferences(state.get("preferences"))
    weather_summary = _summarize_weather(state.get("weather"))
    print("=== DESTINATION EXPLORER ===")
    print(f"requested_destination = {destination}")
    print(f"normalized_destination = {normalize_place_name(destination)}")
    print(f"destination_used_for_llm = {destination}")

    osm_places_raw = state.get("osm_places")
    osm_places = [place for place in _as_list(osm_places_raw) if isinstance(place, dict)]
    if not osm_places:
        recommendations = state.get("recommendations", []) or []
        if isinstance(recommendations, list):
            for block in recommendations:
                if not isinstance(block, dict):
                    continue
                for key in ("hotels", "restaurants", "attractions"):
                    items = block.get(key, []) or []
                    if isinstance(items, list):
                        osm_places.extend(item for item in items if isinstance(item, dict))

    osm_places = validate_destination_places(destination, _dedupe_places(_extract_destination_places(state, osm_places)))
    candidate_places = _serialize_candidates(osm_places, limit=60)
    logger.info(
        "[DEST_EXPLORER] destination=%s osm_places=%d candidates=%d preferences=%s",
        destination,
        len(osm_places),
        len(candidate_places),
        user_preferences,
    )

    prompt = _build_prompt(
        destination=destination,
        trip_days=trip_days,
        user_preferences=user_preferences,
        weather_summary=weather_summary,
        candidate_places=candidate_places,
    )

    raw_text = await _call_nvidia_json(prompt, temperature=0.25, timeout_seconds=5.0)
    parsed = _parse_ranked_payload(raw_text) if raw_text else {}

    ranked = {
        "top_attractions": _normalize_output_places(parsed.get("top_attractions"), category="attraction"),
        "hidden_gems": _normalize_output_places(parsed.get("hidden_gems"), category="attraction"),
        "restaurants": _normalize_output_places(parsed.get("restaurants"), category="restaurant"),
        "hotels": _normalize_output_places(parsed.get("hotels"), category="hotel"),
        "evening_places": _normalize_output_places(parsed.get("evening_places"), category="attraction"),
        "rainy_day_places": _normalize_output_places(parsed.get("rainy_day_places"), category="attraction"),
        "scenic_places": _normalize_output_places(parsed.get("scenic_places"), category="attraction"),
    }

    if not any(ranked.values()):
        buckets = _classify_buckets(osm_places)
        ranked = {
            "top_attractions": buckets["top_attractions"][: min(6, len(buckets["top_attractions"]))],
            "hidden_gems": buckets["hidden_gems"][: min(4, len(buckets["hidden_gems"]))],
            "restaurants": buckets["restaurants"][: min(6, len(buckets["restaurants"]))],
            "hotels": buckets["hotels"][: min(4, len(buckets["hotels"]))],
            "evening_places": buckets["evening_places"][: min(4, len(buckets["evening_places"]))],
            "rainy_day_places": buckets["rainy_day_places"][: min(4, len(buckets["rainy_day_places"]))],
            "scenic_places": buckets["scenic_places"][: min(4, len(buckets["scenic_places"]))],
        }

    targets = {
        "top_attractions": max(4, trip_days * 2),
        "hidden_gems": 3,
        "restaurants": max(4, trip_days * 2),
        "hotels": 4,
        "evening_places": 3,
        "rainy_day_places": 3,
        "scenic_places": max(3, trip_days),
    }

    final: dict[str, list[dict[str, Any]]] = {}
    for key, target in targets.items():
        existing = ranked.get(key, [])
        if len(existing) < target:
            existing.extend(
                _generate_fallback_places(
                    destination,
                    category=key,
                    needed=target - len(existing),
                    seed_catalog=state.get("recommendation_catalog") if isinstance(state.get("recommendation_catalog"), dict) else None,
                )
            )
        validated = validate_destination_places(destination, existing)
        if len(validated) < target:
            validated.extend(
                _generate_fallback_places(
                    destination,
                    category=key,
                    needed=target - len(validated),
                    seed_catalog=state.get("recommendation_catalog") if isinstance(state.get("recommendation_catalog"), dict) else None,
                )
            )
        final[key] = validate_destination_places(destination, validated)[:target]

    logger.info(
        "[DEST_EXPLORER] final counts top=%d hidden=%d restaurants=%d hotels=%d evening=%d rainy=%d scenic=%d",
        len(final["top_attractions"]),
        len(final["hidden_gems"]),
        len(final["restaurants"]),
        len(final["hotels"]),
        len(final["evening_places"]),
        len(final["rainy_day_places"]),
        len(final["scenic_places"]),
    )
    logger.info(
        "[DEST_EXPLORER] sample top=%s restaurants=%s hotels=%s",
        [item.get("name") for item in final["top_attractions"][:5]],
        [item.get("name") for item in final["restaurants"][:5]],
        [item.get("name") for item in final["hotels"][:5]],
    )
    logger.info(
        "[DEST_EXPLORER] first_5_selected_places=%s",
        [item.get("name") for item in (final["top_attractions"] + final["restaurants"] + final["hotels"])[:5]],
    )

    state["destination_explorer"] = final
    state["osm_places"] = osm_places
    return state
