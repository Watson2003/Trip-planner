from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime
from typing import Any

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from tools import generate_pdf_report as build_pdf_report


load_dotenv()

mcp = FastMCP("road-trip-tools")
ORS_BASE_URL = "https://api.openrouteservice.org"
NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org"
OPENWEATHER_BASE_URL = "https://api.openweathermap.org/data/2.5/forecast"
INR_PER_USD = 83.0


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} is not set in the environment.")
    return value


async def _geocode_place(client: httpx.AsyncClient, place: str, api_key: str) -> list[float]:
    """Use ORS geocoding to resolve a place name into [lon, lat]."""
    response = await client.get(
        f"{ORS_BASE_URL}/geocode/search",
        params={"text": place, "size": 1},
        headers={"Authorization": api_key},
    )
    response.raise_for_status()
    payload = response.json()
    features = payload.get("features", [])
    if not features:
        raise ValueError(f"Could not geocode location: {place}")
    lon, lat = features[0]["geometry"]["coordinates"]
    return [lon, lat]


@mcp.tool()
async def get_route(origin: str, destination: str, waypoints: list[str]) -> dict[str, Any]:
    """Return a GeoJSON route from ORS for origin -> waypoints -> destination."""
    api_key = _require_env("OPENROUTESERVICE_API_KEY")
    places = [origin, *waypoints[:2], destination]

    async with httpx.AsyncClient(timeout=30.0) as client:
        coordinates = [await _geocode_place(client, place, api_key) for place in places]
        response = await client.post(
            f"{ORS_BASE_URL}/v2/directions/driving-car/geojson",
            json={"coordinates": coordinates},
            headers={"Authorization": api_key, "Content-Type": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()

    feature = payload["features"][0]
    segment = feature["properties"]["segments"][0]
    # Add a small summary alongside the raw GeoJSON so callers can use the response directly.
    feature["properties"]["summary"] = {
        "distance_km": round(segment["distance"] / 1000.0, 2),
        "duration_hours": round(segment["duration"] / 3600.0, 2),
        "toll_roads": bool(segment.get("tollways", False)),
    }
    return payload


@mcp.tool()
async def get_weather(location: str, days: int) -> dict[str, Any]:
    """Return a grouped 5-day OpenWeatherMap forecast for the requested location."""
    api_key = _require_env("OPENWEATHERMAP_API_KEY")
    days = max(1, min(days, 5))

    async with httpx.AsyncClient(timeout=25.0) as client:
        response = await client.get(
            OPENWEATHER_BASE_URL,
            params={"q": location, "appid": api_key, "units": "metric"},
            headers={"User-Agent": "TripPlanner/1.0"},
        )
        response.raise_for_status()
        payload = response.json()

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in payload.get("list", []):
        date_key = datetime.fromtimestamp(item["dt"]).date().isoformat()
        grouped[date_key].append(
            {
                "time": datetime.fromtimestamp(item["dt"]).isoformat(),
                "temp_celsius": round(item["main"]["temp"], 1),
                "condition": item["weather"][0]["description"],
                "humidity": item["main"]["humidity"],
                "wind_speed": item["wind"]["speed"],
            }
        )

    forecast_days: list[dict[str, Any]] = []
    for index, (date_key, entries) in enumerate(grouped.items()):
        if index >= days:
            break
        temps = [entry["temp_celsius"] for entry in entries]
        conditions = [entry["condition"] for entry in entries]
        severe = next((cond for cond in conditions if _is_severe_weather(cond)), None)
        forecast_days.append(
            {
                "location": payload.get("city", {}).get("name", location),
                "date": date_key,
                "temp_celsius": {
                    "min": round(min(temps), 1),
                    "max": round(max(temps), 1),
                    "avg": round(sum(temps) / len(temps), 1),
                },
                "condition": conditions[0] if conditions else "unknown",
                "alert": severe,
                "entries": entries,
            }
        )

    return {
        "location": payload.get("city", {}).get("name", location),
        "days": forecast_days,
    }


def _is_severe_weather(description: str) -> bool:
    lowered = description.lower()
    return any(word in lowered for word in ["storm", "thunder", "snow", "hail", "extreme", "tornado"])


@mcp.tool()
async def search_places(query: str, location: str, category: str) -> dict[str, Any]:
    """Find nearby hotels, restaurants, or attractions using Nominatim."""
    user_agent = "AI-Road-Trip-Planner/1.0"
    async with httpx.AsyncClient(timeout=25.0, headers={"User-Agent": user_agent}) as client:
        geo = await client.get(
            f"{NOMINATIM_BASE_URL}/search",
            params={"q": location, "format": "jsonv2", "limit": 1},
        )
        geo.raise_for_status()
        geo_payload = geo.json()
        if not geo_payload:
            raise ValueError(f"Could not geocode location: {location}")

        lat = float(geo_payload[0]["lat"])
        lon = float(geo_payload[0]["lon"])
        offset = 0.35
        viewbox = f"{lon - offset},{lat + offset},{lon + offset},{lat - offset}"

        search_query = f"{category} {query}".strip()
        response = await client.get(
            f"{NOMINATIM_BASE_URL}/search",
            params={
                "q": search_query,
                "format": "jsonv2",
                "limit": 10,
                "addressdetails": 1,
                "extratags": 1,
                "viewbox": viewbox,
                "bounded": 1,
            },
        )
        response.raise_for_status()
        results = response.json()

    places: list[dict[str, Any]] = []
    for item in results:
        places.append(
            {
                "name": item.get("display_name", "").split(",")[0],
                "display_name": item.get("display_name"),
                "lat": float(item["lat"]),
                "lon": float(item["lon"]),
                "category": category,
                "type": item.get("type"),
                "tags": item.get("extratags", {}),
            }
        )

    return {"location": location, "query": query, "category": category, "results": places}


@mcp.tool()
def calculate_fuel_cost(distance_km: float, fuel_efficiency_kmpl: float, fuel_price_per_litre: float) -> dict[str, float]:
    """Pure fuel cost calculation in INR and USD."""
    if fuel_efficiency_kmpl <= 0:
        raise ValueError("fuel_efficiency_kmpl must be greater than zero.")

    litres_needed = distance_km / fuel_efficiency_kmpl
    cost_inr = litres_needed * fuel_price_per_litre
    return {
        "distance_km": round(distance_km, 2),
        "fuel_efficiency_kmpl": round(fuel_efficiency_kmpl, 2),
        "fuel_price_per_litre": round(fuel_price_per_litre, 2),
        "litres_needed": round(litres_needed, 2),
        "cost_inr": round(cost_inr, 2),
        "cost_usd": round(cost_inr / INR_PER_USD, 2),
    }


@mcp.tool()
def generate_pdf_report(trip_data: dict[str, Any], output_path: str) -> dict[str, Any]:
    """Generate a styled PDF summary for a road trip."""
    return build_pdf_report(trip_data, output_path)


if __name__ == "__main__":
    mcp.run()
