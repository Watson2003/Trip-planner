from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Query

from agents.fallbacks import fallback_route, fallback_route_road
from agents.route_agent import _coords_from_value, _fetch_route, validate_route_direction
from agents.weather_agent import fetch_weather_forecast
from utils.places import get_coordinates
from utils.destination_discovery import discover_destination_place_catalog
from tools.osm_places import fetch_osm_places, normalize_place_name
from utils.destination_places import validate_destination_places
from utils.recommendations import build_destination_recommendations


router = APIRouter(prefix="/api/debug", tags=["debug"])


@router.get("/recommendations")
async def debug_recommendations(destination: str = Query(..., min_length=1)) -> dict:
    catalog = await build_destination_recommendations(destination)
    return {
        "destination": catalog["destination"],
        "hotels_count": len(catalog["hotels"]),
        "restaurants_count": len(catalog["restaurants"]),
        "attractions_count": len(catalog["attractions"]),
        "fallback_generated": bool(catalog.get("fallback_generated", False)),
        "hotels": catalog["hotels"],
        "restaurants": catalog["restaurants"],
        "attractions": catalog["attractions"],
    }


@router.get("/destination-flow")
async def debug_destination_flow(
    origin: str = Query(..., min_length=1),
    destination: str = Query(..., min_length=1),
) -> dict:
    catalog = await build_destination_recommendations(destination)
    osm_places = await fetch_osm_places(destination, radius_km=15)
    selected_attractions = catalog["attractions"][:5]
    selected_restaurants = catalog["restaurants"][:5]
    selected_hotels = catalog["hotels"][:5]

    all_selected = [*selected_attractions, *selected_restaurants, *selected_hotels]
    invalid_cross_destination_places = [
        place.get("name", "")
        for place in all_selected
        if not validate_destination_places(destination, [place])
    ]

    return {
        "requested_origin": origin,
        "requested_destination": destination,
        "normalized_destination": normalize_place_name(destination),
        "osm_places_count": len(osm_places),
        "fallback_used": bool(catalog.get("fallback_generated", False)),
        "llm_provider": "nvidia_llama",
        "selected_attractions": [place.get("name", "") for place in selected_attractions],
        "selected_restaurants": [place.get("name", "") for place in selected_restaurants],
        "selected_hotels": [place.get("name", "") for place in selected_hotels],
        "invalid_cross_destination_places": invalid_cross_destination_places,
    }


@router.get("/place-discovery")
async def debug_place_discovery(destination: str = Query(..., min_length=1)) -> dict:
    catalog = await discover_destination_place_catalog(destination)
    return {
        "destination": catalog["destination"],
        "normalized_destination": catalog["normalized_destination"],
        "osm_count": catalog["osm_count"],
        "llama_count": catalog["llama_count"],
        "fallback_count": catalog["fallback_count"],
        "final_attractions_count": catalog["final_attractions_count"],
        "final_restaurants_count": catalog["final_restaurants_count"],
        "final_hotels_count": catalog["final_hotels_count"],
        "final_attractions": catalog["final_attractions"],
        "final_restaurants": catalog["final_restaurants"],
        "final_hotels": catalog["final_hotels"],
    }


@router.get("/route")
async def debug_route(
    origin: str = Query(..., min_length=1),
    destination: str = Query(..., min_length=1),
) -> dict:
    try:
        route = await _fetch_route(origin, destination, [])
    except Exception:
        route = await fallback_route_road(origin, destination, [])
        if route is None:
            route = fallback_route(origin, destination, [])
        if route is None:
            route = {
                "polyline": [],
                "origin_coords": None,
                "destination_coords": None,
            }
    origin_lookup, destination_lookup = await get_coordinates(origin), await get_coordinates(destination)
    origin_coords = _coords_from_value(origin_lookup) or _coords_from_value(route.get("origin_coords"))
    destination_coords = _coords_from_value(destination_lookup) or _coords_from_value(route.get("destination_coords"))
    direction_info = validate_route_direction(origin_coords, destination_coords, route.get("polyline", []))
    polyline = direction_info["polyline"]

    return {
        "origin": origin,
        "destination": destination,
        "origin_coords": {"lat": origin_coords[0], "lon": origin_coords[1]} if origin_coords else None,
        "destination_coords": {"lat": destination_coords[0], "lon": destination_coords[1]} if destination_coords else None,
        "first_polyline_point": polyline[0] if polyline else None,
        "last_polyline_point": polyline[-1] if polyline else None,
        "direction_valid": bool(direction_info.get("direction_valid", True)),
        "coordinate_order_fixed": bool(direction_info.get("coordinate_order_fixed", False)),
        "route_direction_fixed": bool(direction_info.get("route_direction_fixed", False)),
        "route_points_count": len(polyline),
    }


@router.get("/weather")
async def debug_weather(
    origin: str = Query(..., min_length=1),
    destination: str = Query(..., min_length=1),
) -> dict:
    today = date.today()
    end_date = today + timedelta(days=4)
    origin_days = await fetch_weather_forecast(origin, today, end_date)
    destination_days = await fetch_weather_forecast(destination, today, end_date)

    origin_first = origin_days[0] if origin_days else {}
    destination_first = destination_days[0] if destination_days else {}

    return {
        "origin_weather": origin_first,
        "destination_weather": destination_first,
        "origin_weather_days": origin_days,
        "destination_weather_days": destination_days,
        "origin_source": origin_first.get("weather_source_used", ""),
        "destination_source": destination_first.get("weather_source_used", ""),
        "empty_weather_fixed": bool(origin_days and destination_days),
    }
