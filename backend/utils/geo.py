from __future__ import annotations

from math import atan2, cos, radians, sin, sqrt
from typing import Any


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in kilometers between two coordinates."""
    r = 6371.0
    d_lat = radians(float(lat2) - float(lat1))
    d_lon = radians(float(lon2) - float(lon1))
    a = sin(d_lat / 2) ** 2 + cos(radians(float(lat1))) * cos(radians(float(lat2))) * sin(d_lon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return round(r * c, 3)


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


def cluster_nearby_places(places: list[dict[str, Any]], max_distance_km: float = 5) -> list[dict[str, Any]]:
    """Group nearby places into simple proximity clusters."""
    valid_places = [place for place in places if isinstance(place, dict)]
    if not valid_places:
        return []

    clusters: list[dict[str, Any]] = []
    for place in valid_places:
        lat, lon = _place_lat_lon(place)
        if lat is None or lon is None:
            clusters.append(
                {
                    "center_latitude": None,
                    "center_longitude": None,
                    "places": [place],
                }
            )
            continue

        assigned = False
        for cluster in clusters:
            center_lat = cluster.get("center_latitude")
            center_lon = cluster.get("center_longitude")
            if center_lat is None or center_lon is None:
                continue
            distance = haversine_distance_km(lat, lon, float(center_lat), float(center_lon))
            if distance <= float(max_distance_km):
                cluster["places"].append(place)
                count = len(cluster["places"])
                cluster["center_latitude"] = round(((float(center_lat) * (count - 1)) + lat) / count, 6)
                cluster["center_longitude"] = round(((float(center_lon) * (count - 1)) + lon) / count, 6)
                assigned = True
                break

        if not assigned:
            clusters.append(
                {
                    "center_latitude": lat,
                    "center_longitude": lon,
                    "places": [place],
                }
            )

    for cluster in clusters:
        cluster["places"].sort(
            key=lambda place: (
                str(place.get("best_time_to_visit") or ""),
                str(place.get("name") or ""),
            )
        )

    return clusters
