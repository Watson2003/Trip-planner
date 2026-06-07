from __future__ import annotations

import asyncio
from typing import Any

import httpx

from agents.fallbacks import fallback_route
from agents.state import TripState
from utils.config import settings


ORS_BASE_URL = "https://api.openrouteservice.org"


async def _geocode_place(client: httpx.AsyncClient, place: str, api_key: str) -> list[float]:
    response = await client.get(
        f"{ORS_BASE_URL}/geocode/search",
        params={
            "api_key": api_key,
            "text": place,
            "boundary.country": "IN",
        },
        headers={"Authorization": api_key},
    )
    response.raise_for_status()
    payload = response.json()
    features = payload.get("features", [])
    if not features:
        raise ValueError(f"Could not geocode location: {place}")
    lon, lat = features[0]["geometry"]["coordinates"]
    return [lon, lat]


async def _fetch_route(origin: str, destination: str) -> dict[str, Any]:
    api_key = settings.openrouteservice_api_key
    if not api_key:
        raise ValueError("OPENROUTESERVICE_API_KEY is not set in the environment.")

    async with httpx.AsyncClient(timeout=2.0) as client:
        origin_coords, destination_coords = await asyncio.gather(
            _geocode_place(client, origin, api_key),
            _geocode_place(client, destination, api_key),
        )
        response = await client.post(
            f"{ORS_BASE_URL}/v2/directions/driving-car/geojson",
            headers={"Authorization": api_key},
            json={
                "coordinates": [origin_coords, destination_coords],
            },
        )
        response.raise_for_status()
        payload = response.json()

    feature = payload["features"][0]
    summary = feature["properties"]["summary"]
    geometry = feature["geometry"]["coordinates"]
    leaflet_coords = [[lat, lng] for lng, lat in geometry]

    return {
        "distance_km": round(summary["distance"] / 1000.0, 2),
        "duration_hours": round(summary["duration"] / 3600.0, 2),
        "coordinates": leaflet_coords,
        "origin_coords": [origin_coords[1], origin_coords[0]],
        "destination_coords": [destination_coords[1], destination_coords[0]],
        "polyline": leaflet_coords,
        "toll_roads": bool(feature.get("properties", {}).get("tollways", False)),
    }


async def route_agent(state: TripState) -> TripState:
    origin = state.get("origin", "")
    destination = state.get("destination", "")
    waypoints = state.get("waypoints", [])[:2]

    if not origin or not destination:
        state.setdefault("errors", []).append("Origin and destination are required for routing.")
        return state

    try:
        route = await asyncio.wait_for(_fetch_route(origin, destination), timeout=2.5)
    except Exception:
        route = fallback_route(origin, destination, waypoints)
        if route is None:
            state.setdefault("errors", []).append(f"Could not build a route for {origin} to {destination}.")
            return state

    state["route_distance_km"] = route["distance_km"]
    state["route_duration_hours"] = route["duration_hours"]
    state["polyline"] = route["polyline"]
    state["toll_roads"] = route["toll_roads"]
    state["route"] = {
        "distance_km": route["distance_km"],
        "duration_hours": route["duration_hours"],
        "coordinates": route.get("coordinates", route["polyline"]),
        "origin_coords": route.get("origin_coords"),
        "destination_coords": route.get("destination_coords"),
        "polyline": route["polyline"],
        "toll_roads": route["toll_roads"],
    }
    return state
