from __future__ import annotations

import asyncio
from typing import Any

import httpx

from agents.fallbacks import fallback_route
from agents.state import TripState
from utils.config import settings


ORS_BASE_URL = "https://api.openrouteservice.org"


async def _fetch_route(origin: str, destination: str, waypoints: list[str]) -> dict[str, Any]:
    api_key = settings.openrouteservice_api_key
    if not api_key:
        raise ValueError("OPENROUTESERVICE_API_KEY is not set in the environment.")

    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json",
    }

    coords = []
    for place in [origin, *waypoints, destination]:
        geocode = await _geocode_place(place, api_key)
        coords.append(geocode)

    body = {"coordinates": coords}
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(f"{ORS_BASE_URL}/v2/directions/driving-car/geojson", json=body, headers=headers)
        response.raise_for_status()
        payload = response.json()

    feature = payload["features"][0]
    properties = feature["properties"]["segments"][0]
    geometry = feature["geometry"]["coordinates"]

    return {
        "distance_km": round(properties["distance"] / 1000.0, 2),
        "duration_hours": round(properties["duration"] / 3600.0, 2),
        "polyline": [[lat, lon] for lon, lat in geometry],
        "toll_roads": bool(properties.get("tollways", False)),
    }


async def _geocode_place(place: str, api_key: str) -> list[float]:
    headers = {"Authorization": api_key}
    params = {"text": place, "size": 1}
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(f"{ORS_BASE_URL}/geocode/search", params=params, headers=headers)
        response.raise_for_status()
        payload = response.json()
    features = payload.get("features", [])
    if not features:
        raise ValueError(f"Could not geocode location: {place}")
    lon, lat = features[0]["geometry"]["coordinates"]
    return [lon, lat]


async def route_agent(state: TripState) -> TripState:
    origin = state.get("origin", "")
    destination = state.get("destination", "")
    waypoints = state.get("waypoints", [])[:2]

    if not origin or not destination:
        state.setdefault("errors", []).append("Origin and destination are required for routing.")
        return state

    try:
        route = await asyncio.wait_for(_fetch_route(origin, destination, waypoints), timeout=8.0)
    except Exception:
        route = fallback_route(origin, destination, waypoints)
        if route is None:
            state.setdefault("errors", []).append(f"Could not build a route for {origin} to {destination}.")
            return state

    state["route_distance_km"] = route["distance_km"]
    state["route_duration_hours"] = route["duration_hours"]
    state["polyline"] = route["polyline"]
    state["toll_roads"] = route["toll_roads"]
    return state
