from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import httpx

from agents.fallbacks import fallback_weather
from agents.state import TripState
from utils.config import settings


OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/forecast"


async def _fetch_forecast(location: str) -> list[dict[str, Any]]:
    if not settings.openweathermap_api_key:
        raise ValueError("OPENWEATHERMAP_API_KEY is not set in the environment.")

    params = {"q": location, "appid": settings.openweathermap_api_key, "units": "metric"}
    async with httpx.AsyncClient(timeout=25.0) as client:
        response = await client.get(OPENWEATHER_URL, params=params)
        response.raise_for_status()
        payload = response.json()

    forecasts = []
    for item in payload.get("list", [])[:5]:
        forecasts.append(
            {
                "location": payload["city"]["name"],
                "date": datetime.fromtimestamp(item["dt"]).date().isoformat(),
                "temp_celsius": round(item["main"]["temp"], 1),
                "condition": item["weather"][0]["description"],
                "alert": _severe_weather_alert(item["weather"][0]["description"]),
            }
        )
    return forecasts


def _severe_weather_alert(description: str) -> str | None:
    lowered = description.lower()
    if any(word in lowered for word in ["storm", "rain", "snow", "thunder", "extreme", "hail", "wind"]):
        return f"Potential severe weather: {description}"
    return None


async def weather_agent(state: TripState) -> TripState:
    locations = [state.get("origin"), state.get("destination"), *(state.get("waypoints", [])[:2])]
    weather: list[dict[str, Any]] = []
    seen: set[str] = set()

    for location in locations:
        if not location or location in seen:
            continue
        seen.add(location)
        try:
            forecasts = await asyncio.wait_for(_fetch_forecast(location), timeout=5.0)
        except Exception:
            forecasts = fallback_weather(location, days=1)
        weather.extend(forecasts[:1])

    state["weather"] = weather
    return state
