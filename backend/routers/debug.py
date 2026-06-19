from __future__ import annotations

from fastapi import APIRouter, Query

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
