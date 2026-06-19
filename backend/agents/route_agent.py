from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Any

from agents.fallbacks import fallback_route, fallback_route_road
from agents.state import TripState
from utils.geo import haversine_distance_km
from utils.places import get_coordinates
from utils.mcp_bridge import mcp_get_route


logger = logging.getLogger(__name__)


def _coords_from_mapping(value: dict[str, Any] | None) -> tuple[float | None, float | None]:
    if not isinstance(value, dict):
        return None, None
    lat = value.get("lat") if value.get("lat") is not None else value.get("latitude")
    lon = value.get("lng") if value.get("lng") is not None else value.get("lon") if value.get("lon") is not None else value.get("longitude")
    if lat is None or lon is None:
        return None, None
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None, None


def _coords_from_value(value: Any) -> tuple[float | None, float | None]:
    if isinstance(value, dict):
        return _coords_from_mapping(value)
    if isinstance(value, Sequence) and len(value) >= 2:
        try:
            return float(value[0]), float(value[1])
        except (TypeError, ValueError):
            return None, None
    return None, None


async def _fallback_route_from_geocodes(origin: str, destination: str, waypoints: list[str]) -> dict[str, Any] | None:
    stops = [origin, *waypoints[:2], destination]
    resolved_points: list[tuple[float, float]] = []

    for stop in stops:
        coords = await get_coordinates(stop)
        lat, lon = _coords_from_value(coords)
        if lat is None or lon is None:
            continue
        resolved_points.append((lat, lon))

    if len(resolved_points) < 2:
        return None

    distance_km = 0.0
    for index, current in enumerate(resolved_points):
        if index > 0:
            previous = resolved_points[index - 1]
            distance_km += haversine_distance_km(previous[0], previous[1], current[0], current[1])

    polyline = [[round(lat, 6), round(lon, 6)] for lat, lon in resolved_points]
    return {
        "distance_km": round(distance_km, 2),
        "duration_hours": round(max(1.0, distance_km / 55.0), 2),
        "coordinates": polyline,
        "origin_coords": polyline[0],
        "destination_coords": polyline[-1],
        "polyline": polyline,
        "toll_roads": distance_km > 250,
    }


def _reverse_if_needed(polyline: list[list[float]], origin_coords: tuple[float, float] | None, destination_coords: tuple[float, float] | None) -> list[list[float]]:
    if len(polyline) < 2 or origin_coords is None or destination_coords is None:
        return polyline

    start_lat, start_lon = polyline[0]
    end_lat, end_lon = polyline[-1]

    forward_score = haversine_distance_km(start_lat, start_lon, origin_coords[0], origin_coords[1]) + haversine_distance_km(end_lat, end_lon, destination_coords[0], destination_coords[1])
    reversed_score = haversine_distance_km(start_lat, start_lon, destination_coords[0], destination_coords[1]) + haversine_distance_km(end_lat, end_lon, origin_coords[0], origin_coords[1])

    if reversed_score + 0.5 < forward_score:
        return list(reversed(polyline))
    return polyline


def validate_route_direction(
    origin_coords: tuple[float, float] | None,
    destination_coords: tuple[float, float] | None,
    polyline: list[list[float]],
) -> dict[str, Any]:
    fixed_polyline = _reverse_if_needed(list(polyline), origin_coords, destination_coords)
    direction_valid = fixed_polyline == polyline
    coordinate_order_fixed = not direction_valid
    return {
        "direction_valid": direction_valid,
        "coordinate_order_fixed": coordinate_order_fixed,
        "polyline": fixed_polyline,
        "route_direction_fixed": coordinate_order_fixed,
    }


async def _fetch_route(origin: str, destination: str, waypoints: list[str]) -> dict[str, Any]:
    payload = await asyncio.wait_for(
        mcp_get_route(origin=origin, destination=destination, waypoints=waypoints[:2]),
        timeout=10.0,
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
        route = await fallback_route_road(origin, destination, waypoints)
        if route is None:
            route = fallback_route(origin, destination, waypoints)
        if route is None:
            route = await _fallback_route_from_geocodes(origin, destination, waypoints)
        if route is None:
            state.setdefault("errors", []).append(f"Could not build a route for {origin} to {destination}.")
            return state

    origin_lookup, destination_lookup = await asyncio.gather(get_coordinates(origin), get_coordinates(destination))
    origin_coords = _coords_from_value(origin_lookup) or _coords_from_value(route.get("origin_coords"))
    destination_coords = _coords_from_value(destination_lookup) or _coords_from_value(route.get("destination_coords"))
    polyline = route["polyline"]
    if origin_coords and destination_coords:
        direction_info = validate_route_direction(origin_coords, destination_coords, polyline)
        polyline = direction_info["polyline"]
    else:
        direction_info = {
            "direction_valid": True,
            "coordinate_order_fixed": False,
            "route_direction_fixed": False,
        }

    resolved_origin = origin_coords or (tuple(polyline[0]) if polyline else None)
    resolved_destination = destination_coords or (tuple(polyline[-1]) if polyline else None)

    if resolved_origin and resolved_destination:
        logger.info(
            "route endpoints resolved origin_name=%s destination_name=%s origin_lat=%s origin_lon=%s destination_lat=%s destination_lon=%s",
            origin,
            destination,
            resolved_origin[0],
            resolved_origin[1],
            resolved_destination[0],
            resolved_destination[1],
        )
        print(f"origin_name = {origin}")
        print(f"destination_name = {destination}")
        print(f"origin_lat = {resolved_origin[0]}")
        print(f"origin_lon = {resolved_origin[1]}")
        print(f"destination_lat = {resolved_destination[0]}")
        print(f"destination_lon = {resolved_destination[1]}")
        print(f"first_polyline_coordinate = {polyline[0] if polyline else None}")
        print(f"last_polyline_coordinate = {polyline[-1] if polyline else None}")
        print(f"total_coordinate_count = {len(polyline)}")
        print(f"route_direction_fixed = {str(direction_info.get('route_direction_fixed', False)).lower()}")

    state["route_distance_km"] = route["distance_km"]
    state["route_duration_hours"] = route["duration_hours"]
    state["polyline"] = polyline
    state["toll_roads"] = route["toll_roads"]
    state["route"] = {
        "distance_km": route["distance_km"],
        "duration_hours": route["duration_hours"],
        "coordinates": polyline,
        "origin_coords": resolved_origin,
        "destination_coords": resolved_destination,
        "polyline": polyline,
        "toll_roads": route["toll_roads"],
        "direction_valid": direction_info.get("direction_valid", True),
        "coordinate_order_fixed": direction_info.get("coordinate_order_fixed", False),
        "route_direction_fixed": direction_info.get("route_direction_fixed", False),
        "route_points_count": len(polyline),
    }
    return state
