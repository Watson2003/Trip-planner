from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from math import asin, cos, radians, sin, sqrt
from typing import Any

import httpx


@dataclass(frozen=True)
class Coordinates:
    lat: float
    lng: float


CITY_COORDINATES: dict[str, Coordinates] = {
    "mumbai": Coordinates(19.0760, 72.8777),
    "goa": Coordinates(15.4909, 73.8278),
    "panaji": Coordinates(15.4909, 73.8278),
    "delhi": Coordinates(28.6139, 77.2090),
    "new delhi": Coordinates(28.6139, 77.2090),
    "bengaluru": Coordinates(12.9716, 77.5946),
    "bangalore": Coordinates(12.9716, 77.5946),
    "chennai": Coordinates(13.0827, 80.2707),
    "tiruchirappalli": Coordinates(10.7905, 78.7047),
    "trichy": Coordinates(10.7905, 78.7047),
    "hyderabad": Coordinates(17.3850, 78.4867),
    "pune": Coordinates(18.5204, 73.8567),
    "jaipur": Coordinates(26.9124, 75.7873),
    "jodhpur": Coordinates(26.2389, 73.0243),
    "jaisalmer": Coordinates(26.9157, 70.9083),
    "udaipur": Coordinates(24.5854, 73.7125),
    "kolkata": Coordinates(22.5726, 88.3639),
    "ahmedabad": Coordinates(23.0225, 72.5714),
    "indore": Coordinates(22.7196, 75.8577),
    "surat": Coordinates(21.1702, 72.8311),
    "nagpur": Coordinates(21.1458, 79.0882),
    "kochi": Coordinates(9.9312, 76.2673),
    "cochin": Coordinates(9.9312, 76.2673),
    "thiruvananthapuram": Coordinates(8.5241, 76.9366),
    "mysuru": Coordinates(12.2958, 76.6394),
    "mysore": Coordinates(12.2958, 76.6394),
    "manali": Coordinates(32.2396, 77.1887),
    "shimla": Coordinates(31.1048, 77.1734),
    "coorg": Coordinates(12.4244, 75.7382),
    "madikeri": Coordinates(12.4244, 75.7382),
    "ooty": Coordinates(11.4102, 76.6950),
    "coimbatore": Coordinates(11.0168, 76.9558),
    "erode": Coordinates(11.3410, 77.7172),
    "karur": Coordinates(10.9577, 78.0801),
    "palani": Coordinates(10.4500, 77.5209),
    "pollachi": Coordinates(10.6582, 77.0081),
    "mettupalayam": Coordinates(11.2997, 76.9346),
    "avinashi": Coordinates(11.1914, 77.2680),
    "tiruppur": Coordinates(11.1085, 77.3411),
    "salem": Coordinates(11.6643, 78.1460),
    "munnar": Coordinates(10.0889, 77.0595),
    "leh": Coordinates(34.1526, 77.5771),
    "rishikesh": Coordinates(30.0869, 78.2676),
    "hampi": Coordinates(15.3350, 76.4600),
    "port blair": Coordinates(11.6234, 92.7265),
    "andaman": Coordinates(11.6234, 92.7265),
    "srinagar": Coordinates(34.0837, 74.7973),
    "agra": Coordinates(27.1767, 78.0081),
    "varanasi": Coordinates(25.3176, 82.9739),
}


def normalize_text(value: str) -> str:
    return " ".join(value.lower().replace(",", " ").split())


def lookup_coordinates(place: str) -> Coordinates | None:
    normalized = normalize_text(place)
    if not normalized:
        return None

    if normalized in CITY_COORDINATES:
        return CITY_COORDINATES[normalized]

    for key, coordinates in CITY_COORDINATES.items():
        if key in normalized:
            return coordinates
    return None


def haversine_km(origin: Coordinates, destination: Coordinates) -> float:
    earth_radius_km = 6371.0
    lat1 = radians(origin.lat)
    lat2 = radians(destination.lat)
    delta_lat = radians(destination.lat - origin.lat)
    delta_lng = radians(destination.lng - origin.lng)

    a = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lng / 2) ** 2
    c = 2 * asin(min(1.0, sqrt(a)))
    return earth_radius_km * c


def interpolate_points(origin: Coordinates, destination: Coordinates, steps: int = 4) -> list[list[float]]:
    if steps < 2:
        return [[origin.lat, origin.lng], [destination.lat, destination.lng]]

    points: list[list[float]] = []
    for index in range(steps + 1):
        ratio = index / steps
        lat = origin.lat + (destination.lat - origin.lat) * ratio
        lng = origin.lng + (destination.lng - origin.lng) * ratio
        points.append([round(lat, 6), round(lng, 6)])
    return points


def _clean_stops(origin: str, waypoints: list[str], destination: str) -> list[str]:
    stops = [origin, *waypoints[:2], destination]
    cleaned: list[str] = []
    for stop in stops:
        stop = stop.strip()
        if stop and (not cleaned or cleaned[-1].casefold() != stop.casefold()):
            cleaned.append(stop)
    return cleaned


def _route_geometry_from_points(points: Sequence[Coordinates]) -> list[list[float]]:
    polyline: list[list[float]] = []
    for index, current in enumerate(points):
        if index == 0:
            polyline.append([round(current.lat, 6), round(current.lng, 6)])
            continue

        previous = points[index - 1]
        segment = interpolate_points(previous, current, steps=6)
        if polyline:
            polyline.extend(segment[1:])
        else:
            polyline.extend(segment)
    return polyline


async def fallback_route_road(origin: str, destination: str, waypoints: list[str]) -> dict[str, Any] | None:
    """Try a lightweight OSRM road route before falling back to straight-line interpolation."""
    stops = _clean_stops(origin, waypoints, destination)
    coordinates: list[Coordinates] = []
    for stop in stops:
      coord = lookup_coordinates(stop)
      if coord is None:
          return None
      coordinates.append(coord)

    if len(coordinates) < 2:
        return None

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            coord_string = ";".join(f"{point.lng},{point.lat}" for point in coordinates)
            response = await client.get(
                f"https://router.project-osrm.org/route/v1/driving/{coord_string}",
                params={
                    "overview": "full",
                    "geometries": "geojson",
                    "steps": "false",
                    "alternatives": "false",
                },
            )
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return None

    routes = payload.get("routes") or []
    if not routes:
        return None

    route = routes[0]
    geometry = (route.get("geometry") or {}).get("coordinates") or []
    polyline = [[round(lat, 6), round(lng, 6)] for lng, lat in geometry if isinstance(lng, (int, float)) and isinstance(lat, (int, float))]
    if len(polyline) < 2:
        return None

    return {
        "distance_km": round(float(route.get("distance", 0.0)) / 1000.0, 2),
        "duration_hours": round(float(route.get("duration", 0.0)) / 3600.0, 2),
        "polyline": polyline,
        "toll_roads": float(route.get("distance", 0.0)) > 250000,
    }


def fallback_route(origin: str, destination: str, waypoints: list[str]) -> dict[str, Any] | None:
    stops = _clean_stops(origin, waypoints, destination)
    coordinates: list[Coordinates] = []
    for stop in stops:
        coord = lookup_coordinates(stop)
        if coord is not None:
            coordinates.append(coord)

    if len(coordinates) < 2:
        return None

    distance_km = 0.0
    for index, current in enumerate(coordinates):
        if index > 0:
            previous = coordinates[index - 1]
            distance_km += haversine_km(previous, current)

    polyline = _route_geometry_from_points(coordinates)
    duration_hours = max(1.0, round(distance_km / 55.0, 2))
    return {
        "distance_km": round(distance_km, 2),
        "duration_hours": duration_hours,
        "polyline": polyline,
        "toll_roads": distance_km > 250,
    }


def classify_location(location: str) -> str:
    normalized = normalize_text(location)
    if any(keyword in normalized for keyword in ["goa", "cochin", "kochi", "chennai", "andaman"]):
        return "coastal"
    if any(keyword in normalized for keyword in ["manali", "shimla", "ooty", "munnar", "coorg", "leh", "rishikesh"]):
        return "hill"
    if any(keyword in normalized for keyword in ["jaipur", "jodhpur", "jaisalmer", "udaipur"]):
        return "desert"
    if any(keyword in normalized for keyword in ["delhi", "mumbai", "pune", "hyderabad", "bengaluru", "bangalore"]):
        return "metro"
    return "mixed"


def fallback_weather(location: str, days: int = 5, start_date: date | None = None) -> list[dict[str, Any]]:
    profile = classify_location(location)
    base_date = start_date or date.today()

    if profile == "coastal":
        base_min, base_max, condition = 25.0, 32.0, "partly cloudy"
    elif profile == "hill":
        base_min, base_max, condition = 11.0, 22.0, "cool and cloudy"
    elif profile == "desert":
        base_min, base_max, condition = 21.0, 36.0, "clear sky"
    elif profile == "metro":
        base_min, base_max, condition = 23.0, 33.0, "light cloud cover"
    else:
        base_min, base_max, condition = 20.0, 31.0, "scattered clouds"

    forecasts: list[dict[str, Any]] = []
    for index in range(days):
        date_value = base_date + timedelta(days=index)
        swing = 1.5 + (index % 3)
        min_temp = round(base_min - swing, 1)
        max_temp = round(base_max + swing, 1)
        avg_temp = round((min_temp + max_temp) / 2, 1)
        description = condition if index % 2 == 0 else f"{condition} with mild breeze"
        alert = "Potential rain showers" if profile == "coastal" and index % 2 == 0 else None
        forecasts.append(
            {
                "location": location,
                "date": date_value.isoformat(),
                "temp_celsius": {
                    "min": min_temp,
                    "max": max_temp,
                    "avg": avg_temp,
                },
                "condition": description,
                "alert": alert,
            }
        )

    return forecasts


def fallback_daily_weather(location: str, days: int = 5, start_date: date | None = None) -> list[dict[str, Any]]:
    base_date = start_date or date.today()
    profile = classify_location(location)

    if profile == "coastal":
        base_min, base_max, condition, icon = 25.0, 32.0, "partly cloudy", "⛅"
    elif profile == "hill":
        base_min, base_max, condition, icon = 11.0, 22.0, "cool and cloudy", "🌥️"
    elif profile == "desert":
        base_min, base_max, condition, icon = 21.0, 36.0, "clear sky", "☀️"
    elif profile == "metro":
        base_min, base_max, condition, icon = 23.0, 33.0, "light cloud cover", "🌤️"
    else:
        base_min, base_max, condition, icon = 20.0, 31.0, "scattered clouds", "⛅"

    forecasts: list[dict[str, Any]] = []
    for index in range(days):
        forecast_date = base_date + timedelta(days=index)
        swing = 1.2 + (index % 3)
        temp_min = round(base_min - swing, 1)
        temp_max = round(base_max + swing, 1)
        temp_feels = round((temp_min + temp_max) / 2, 1)
        humidity = int(55 + (index * 4) % 20)
        rain_chance = 10 + ((index + 1) * 9) % 45
        weather_condition = condition if index % 2 == 0 else f"{condition} with mild breeze"
        alert = "Potential rain showers" if rain_chance > 45 else None
        forecasts.append(
            {
                "date": forecast_date.isoformat(),
                "day_name": forecast_date.strftime("%A"),
                "location": location,
                "temp_min_celsius": temp_min,
                "temp_max_celsius": temp_max,
                "temp_feels_like": temp_feels,
                "humidity_percent": humidity,
                "condition": weather_condition,
                "weather_icon": icon,
                "wind_speed_kmh": round(8.0 + index * 1.5, 1),
                "rain_chance_percent": rain_chance,
                "alert": alert,
            }
        )

    return forecasts


def fallback_weather_forecast_response(location: str, days: int = 5) -> dict[str, Any]:
    forecasts = fallback_weather(location, days=days)
    return {
        "location": location,
        "days": [
            {
                "location": forecast["location"],
                "date": forecast["date"],
                "temp_celsius": forecast["temp_celsius"],
                "condition": forecast["condition"],
                "alert": forecast["alert"],
                "entries": [
                    {
                        "time": forecast["date"],
                        "temp_celsius": forecast["temp_celsius"]["avg"],
                        "condition": forecast["condition"],
                        "humidity": 55,
                        "wind_speed": 10.0,
                    }
                ],
            }
            for forecast in forecasts
        ],
    }
