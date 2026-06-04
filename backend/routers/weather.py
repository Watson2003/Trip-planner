from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, status

from agents.fallbacks import fallback_weather_forecast_response
from models.schemas import WeatherForecastResponse
from utils.config import settings

router = APIRouter(tags=["weather"])
OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/forecast"


@router.get("/weather/{location}", response_model=WeatherForecastResponse)
async def get_weather(location: str) -> WeatherForecastResponse:
    if not settings.openweathermap_api_key:
        return WeatherForecastResponse.model_validate(fallback_weather_forecast_response(location))

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await asyncio.wait_for(
                client.get(
                    OPENWEATHER_URL,
                    params={"q": location, "appid": settings.openweathermap_api_key, "units": "metric"},
                ),
                timeout=5.0,
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        if status_code == 404:
            return WeatherForecastResponse.model_validate(fallback_weather_forecast_response(location))
        return WeatherForecastResponse.model_validate(fallback_weather_forecast_response(location))
    except httpx.HTTPError as exc:
        return WeatherForecastResponse.model_validate(fallback_weather_forecast_response(location))

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in payload.get("list", []):
        date_key = datetime.fromtimestamp(item["dt"]).date().isoformat()
        grouped.setdefault(date_key, []).append(
            {
                "time": datetime.fromtimestamp(item["dt"]).isoformat(),
                "temp_celsius": round(item["main"]["temp"], 1),
                "condition": item["weather"][0]["description"],
                "humidity": item["main"]["humidity"],
                "wind_speed": item["wind"]["speed"],
            }
        )

    days = []
    for date_key, entries in list(grouped.items())[:5]:
        temps = [entry["temp_celsius"] for entry in entries]
        conditions = [entry["condition"] for entry in entries]
        days.append(
            {
                "location": payload.get("city", {}).get("name", location),
                "date": date_key,
                "temp_celsius": {
                    "min": round(min(temps), 1),
                    "max": round(max(temps), 1),
                    "avg": round(sum(temps) / len(temps), 1),
                },
                "condition": conditions[0] if conditions else "unknown",
                "alert": next((cond for cond in conditions if _is_severe_weather(cond)), None),
                "entries": entries,
            }
        )

    if not days:
        return WeatherForecastResponse.model_validate(fallback_weather_forecast_response(location))

    return WeatherForecastResponse(location=payload.get("city", {}).get("name", location), days=days)


def _is_severe_weather(description: str) -> bool:
    lowered = description.lower()
    return any(word in lowered for word in ["storm", "thunder", "snow", "hail", "extreme", "tornado"])
