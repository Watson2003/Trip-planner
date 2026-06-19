from __future__ import annotations

from math import atan2, cos, radians, sin, sqrt
from typing import Any


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


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in kilometers between two coordinates."""
    earth_radius_km = 6371.0
    d_lat = radians(float(lat2) - float(lat1))
    d_lon = radians(float(lon2) - float(lon1))
    a = sin(d_lat / 2) ** 2 + cos(radians(float(lat1))) * cos(radians(float(lat2))) * sin(d_lon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return round(earth_radius_km * c, 3)


def estimate_travel_time_minutes(distance_km: float, average_speed_kmh: float = 24.0) -> int:
    """Estimate realistic intra-destination travel time."""
    distance = max(0.0, float(distance_km or 0.0))
    if distance <= 0:
        return 0
    speed = max(8.0, float(average_speed_kmh or 24.0))
    minutes = int(round((distance / speed) * 60))
    return max(5, min(90, minutes))


def sort_places_nearest_neighbor(
    places: list[dict[str, Any]],
    *,
    start_lat: float | None = None,
    start_lon: float | None = None,
) -> list[dict[str, Any]]:
    """Sort places by a greedy nearest-neighbor path."""
    candidates = [place for place in places if isinstance(place, dict)]
    if not candidates:
        return []

    remaining = candidates[:]
    ordered: list[dict[str, Any]] = []
    current_lat = start_lat
    current_lon = start_lon

    def _sort_key(place: dict[str, Any]) -> tuple[float, float, float, str]:
        lat, lon = _place_lat_lon(place)
        rating = float(place.get("rating") or 0.0)
        reviews = float(place.get("total_reviews") or 0.0)
        return (
            -(rating or 0.0),
            -(reviews or 0.0),
            float(lat or 0.0),
            str(place.get("name") or ""),
        )

    if current_lat is None or current_lon is None:
        first = sorted(remaining, key=_sort_key)[0]
        ordered.append(first)
        remaining.remove(first)
        current_lat, current_lon = _place_lat_lon(first)

    while remaining:
        if current_lat is None or current_lon is None:
            next_place = sorted(remaining, key=_sort_key)[0]
        else:
            next_place = min(
                remaining,
                key=lambda place: (
                    haversine_distance_km(current_lat, current_lon, *(_place_lat_lon(place) or (current_lat, current_lon))),
                    -float(place.get("rating") or 0.0),
                    -float(place.get("total_reviews") or 0.0),
                    str(place.get("name") or ""),
                ),
            )
        ordered.append(next_place)
        remaining.remove(next_place)
        current_lat, current_lon = _place_lat_lon(next_place)

    return ordered


def cluster_places_by_distance(places: list[dict[str, Any]], max_distance_km: float = 5) -> list[dict[str, Any]]:
    """Group places into proximity-based clusters."""
    valid_places = [place for place in places if isinstance(place, dict)]
    if not valid_places:
        return []

    clusters: list[dict[str, Any]] = []
    threshold = max(0.1, float(max_distance_km))

    for place in valid_places:
        lat, lon = _place_lat_lon(place)
        if lat is None or lon is None:
            clusters.append(
                {
                    "center_latitude": None,
                    "center_longitude": None,
                    "places": [place],
                    "average_distance_km": 0.0,
                }
            )
            continue

        best_cluster = None
        best_distance = None
        for cluster in clusters:
            center_lat = cluster.get("center_latitude")
            center_lon = cluster.get("center_longitude")
            if center_lat is None or center_lon is None:
                continue
            distance = haversine_distance_km(lat, lon, float(center_lat), float(center_lon))
            if distance <= threshold and (best_distance is None or distance < best_distance):
                best_cluster = cluster
                best_distance = distance

        if best_cluster is None:
            clusters.append(
                {
                    "center_latitude": lat,
                    "center_longitude": lon,
                    "places": [place],
                    "average_distance_km": 0.0,
                }
            )
            continue

        best_cluster["places"].append(place)
        count = len(best_cluster["places"])
        center_lat = float(best_cluster["center_latitude"])
        center_lon = float(best_cluster["center_longitude"])
        best_cluster["center_latitude"] = round(((center_lat * (count - 1)) + lat) / count, 6)
        best_cluster["center_longitude"] = round(((center_lon * (count - 1)) + lon) / count, 6)

    for cluster in clusters:
        places_in_cluster = [place for place in cluster["places"] if isinstance(place, dict)]
        cluster["places"] = places_in_cluster
        if not places_in_cluster:
            cluster["average_distance_km"] = 0.0
            continue
        center_lat = cluster.get("center_latitude")
        center_lon = cluster.get("center_longitude")
        if center_lat is None or center_lon is None:
            cluster["average_distance_km"] = 0.0
            continue
        distances = []
        for place in places_in_cluster:
            lat, lon = _place_lat_lon(place)
            if lat is None or lon is None:
                continue
            distances.append(haversine_distance_km(float(center_lat), float(center_lon), lat, lon))
        cluster["average_distance_km"] = round(sum(distances) / len(distances), 3) if distances else 0.0
        cluster["places"] = sort_places_nearest_neighbor(places_in_cluster)

    return clusters
