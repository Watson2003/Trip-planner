from __future__ import annotations

import asyncio
from typing import Any

from agents.fallbacks import fallback_route
from agents.state import TripState
from utils.mcp_bridge import mcp_get_route


async def _fetch_route(origin: str, destination: str, waypoints: list[str]) -> dict[str, Any]:
    payload = await asyncio.wait_for(
        mcp_get_route(origin=origin, destination=destination, waypoints=waypoints[:2]),
        timeout=30.0,
    )

    feature = payload["features"][0]
    summary = feature["properties"]["summary"]
    geometry = feature["geometry"]["coordinates"]
    leaflet_coords = [[lat, lng] for lng, lat in geometry]

    return {
        "distance_km": float(summary["distance_km"]),
        "duration_hours": float(summary["duration_hours"]),
        "coordinates": leaflet_coords,
        "origin_coords": leaflet_coords[0] if leaflet_coords else None,
        "destination_coords": leaflet_coords[-1] if leaflet_coords else None,
        "polyline": leaflet_coords,
        "toll_roads": bool(summary.get("toll_roads", False)),
    }


async def route_agent(state: TripState) -> TripState:
    origin = state.get("origin", "")
    destination = state.get("destination", "")
    waypoints = state.get("waypoints", [])[:2]

    if not origin or not destination:
        state.setdefault("errors", []).append("Origin and destination are required for routing.")
        return state

    try:
        route = await _fetch_route(origin, destination, waypoints)
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
