from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Mapping
from datetime import date, datetime, time, timedelta
from typing import Any

import httpx

from agents.state import TripState
from models.schemas import DailyWeather
from utils.config import settings


logger = logging.getLogger(__name__)

OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/forecast"
TRAVEL_DATES_PATTERN = re.compile(
    r"^\s*(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})\s*$",
    re.IGNORECASE,
)


def _normalize_locations(state: TripState) -> list[str]:
    """Collect unique trip locations in the order they should be forecasted."""
    locations: list[str] = []
    seen: set[str] = set()

    raw_waypoints = state.get("waypoints") or []
    if not isinstance(raw_waypoints, list):
        raw_waypoints = [raw_waypoints]

    for location in [state.get("origin"), state.get("destination"), *raw_waypoints]:
        if not location:
            continue
        normalized = str(location).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        locations.append(normalized)

    return locations


def _parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _parse_travel_date_range(travel_dates: Any) -> tuple[date, date] | None:
    """Support both the current dict shape and the requested 'start to end' string."""
    if isinstance(travel_dates, str):
        match = TRAVEL_DATES_PATTERN.match(travel_dates)
        if not match:
            return None
        return _parse_iso_date(match.group(1)), _parse_iso_date(match.group(2))

    if isinstance(travel_dates, Mapping):
        start_value = travel_dates.get("start") or travel_dates.get("start_date")
        end_value = travel_dates.get("end") or travel_dates.get("end_date")
        if start_value and end_value:
            return _parse_iso_date(str(start_value)), _parse_iso_date(str(end_value))

    start_value = getattr(travel_dates, "start", None)
    end_value = getattr(travel_dates, "end", None)
    if start_value and end_value:
        return _parse_iso_date(str(start_value)), _parse_iso_date(str(end_value))

    return None


def _parse_forecast_datetime(item: dict[str, Any]) -> datetime | None:
    if item.get("dt_txt"):
        try:
            return datetime.strptime(item["dt_txt"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

    dt_value = item.get("dt")
    if isinstance(dt_value, (int, float)):
        return datetime.fromtimestamp(dt_value)

    return None


def _weather_icon(main: str, description: str) -> str:
    """Map OpenWeatherMap weather conditions to a simple visual emoji."""
    main_lower = (main or "").strip().lower()
    description_lower = (description or "").strip().lower()

    if main_lower == "thunderstorm":
        return "⛈️"
    if main_lower == "drizzle":
        return "🌦️"
    if main_lower == "rain":
        return "🌧️"
    if main_lower == "snow":
        return "❄️"
    if main_lower == "clear":
        return "☀️"
    if main_lower == "clouds":
        if any(term in description_lower for term in ["few", "scattered"]):
            return "🌤️"
        if any(term in description_lower for term in ["broken", "overcast"]):
            return "☁️"
        return "🌡️"
    if any(term in main_lower or term in description_lower for term in ["mist", "fog", "haze"]):
        return "🌫️"
    return "🌡️"


def _build_alert(temp_max_celsius: float, wind_speed_kmh: float, rain_chance_percent: int) -> str | None:
    if rain_chance_percent > 70:
        return "Heavy Rain Expected"
    if temp_max_celsius > 35:
        return "Extreme Heat Warning"
    if wind_speed_kmh > 50:
        return "Strong Wind Warning"
    return None


def _representative_entry(entries: list[dict[str, Any]], target_day: date) -> dict[str, Any]:
    noon = datetime.combine(target_day, time(hour=12))

    def _distance(item: dict[str, Any]) -> float:
        forecast_dt = _parse_forecast_datetime(item)
        if forecast_dt is None:
            return float("inf")
        return abs((forecast_dt - noon).total_seconds())

    return min(entries, key=_distance)


def _build_daily_weather(location: str, target_day: date, entries: list[dict[str, Any]]) -> DailyWeather:
    representative = _representative_entry(entries, target_day)
    representative_main = representative.get("weather", [{}])[0] or {}
    condition = str(representative_main.get("description") or representative_main.get("main") or "Unknown")
    weather_main = str(representative_main.get("main") or "")

    temps = [float(entry.get("main", {}).get("temp", 0.0)) for entry in entries]
    feels_like = float(representative.get("main", {}).get("feels_like", 0.0))
    humidity = int(round(float(representative.get("main", {}).get("humidity", 0))))
    wind_speed_kmh = round(float(representative.get("wind", {}).get("speed", 0.0)) * 3.6, 1)
    rain_chance_percent = int(round(max(float(entry.get("pop", 0.0)) for entry in entries) * 100))

    temp_min_celsius = round(min(temps), 1) if temps else 0.0
    temp_max_celsius = round(max(temps), 1) if temps else 0.0
    alert = _build_alert(temp_max_celsius=temp_max_celsius, wind_speed_kmh=wind_speed_kmh, rain_chance_percent=rain_chance_percent)

    return DailyWeather(
        date=target_day.isoformat(),
        day_name=target_day.strftime("%A"),
        location=location,
        temp_min_celsius=temp_min_celsius,
        temp_max_celsius=temp_max_celsius,
        temp_feels_like=round(feels_like, 1),
        humidity_percent=humidity,
        condition=condition,
        weather_icon=_weather_icon(weather_main, condition),
        wind_speed_kmh=wind_speed_kmh,
        rain_chance_percent=rain_chance_percent,
        alert=alert,
    )


async def _fetch_location_weather(
    client: httpx.AsyncClient,
    location: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    if not settings.openweathermap_api_key:
        logger.error("OPENWEATHERMAP_API_KEY is not set in the environment.")
        return []

    try:
        response = await client.get(
            OPENWEATHER_URL,
            params={"q": location, "appid": settings.openweathermap_api_key, "units": "metric"},
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.exception("Failed to fetch weather forecast for %s: %s", location, exc)
        return []

    return filter_openweather_forecast_by_date_range(payload, location, start_date, end_date)


def filter_openweather_forecast_by_date_range(
    payload: dict[str, Any],
    location: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """Convert OpenWeatherMap forecast payload into date-filtered daily weather objects."""
    grouped: dict[date, list[dict[str, Any]]] = {}
    for item in payload.get("list", []):
        forecast_dt = _parse_forecast_datetime(item)
        if forecast_dt is None:
            continue

        forecast_date = forecast_dt.date()
        if not (start_date <= forecast_date <= end_date):
            continue

        grouped.setdefault(forecast_date, []).append(item)

    if not grouped:
        return []

    city_name = str(payload.get("city", {}).get("name") or location)
    weather_days: list[dict[str, Any]] = []

    # Keep only the first five dates so the result stays within the OpenWeatherMap forecast horizon.
    for forecast_date in sorted(grouped.keys())[:5]:
        daily_weather = _build_daily_weather(city_name, forecast_date, grouped[forecast_date])
        daily_payload = daily_weather.model_dump()

        # Preserve a few legacy aliases so existing PDF/report code still renders useful rows.
        daily_payload.update(
            {
                "day": daily_payload["day_name"],
                "city": daily_payload["location"],
                "temperatureC": daily_payload["temp_max_celsius"],
                "temp_celsius": daily_payload["temp_max_celsius"],
                "severeAlert": daily_payload["alert"],
            }
        )
        weather_days.append(daily_payload)

    return weather_days


async def weather_agent(state: TripState) -> TripState:
    travel_dates = _parse_travel_date_range(state.get("travel_dates"))
    if travel_dates is None:
        logger.error("Unable to parse trip travel dates from state: %r", state.get("travel_dates"))
        state["weather"] = []
        state["weather_status"] = "unavailable"
        state["weather_message"] = "Travel dates are missing or invalid."
        return state

    start_date, end_date = travel_dates
    if end_date < start_date:
        logger.error("Trip travel dates are invalid: end date is earlier than start date.")
        state["weather"] = []
        state["weather_status"] = "unavailable"
        state["weather_message"] = "Travel dates are missing or invalid."
        return state

    today = date.today()
    if start_date < today:
        state["weather"] = []
        state["weather_status"] = "past_dates"
        state["weather_message"] = "These travel dates have already passed."
        return state

    if start_date > today + timedelta(days=5):
        state["weather"] = []
        state["weather_status"] = "unavailable"
        state["weather_message"] = (
            "Forecast not available yet. OpenWeatherMap provides forecasts up to 5 days ahead. "
            "Check back closer to your travel date."
        )
        return state

    locations = _normalize_locations(state)
    if not locations:
        state["weather"] = []
        state["weather_status"] = "unavailable"
        state["weather_message"] = "No trip locations were provided."
        return state

    # Keep the end-to-end trip plan responsive; weather should fail fast and fall back to an empty list
    # rather than holding the entire planning request open.
    async with httpx.AsyncClient(timeout=2.0) as client:
        tasks = [_fetch_location_weather(client, location, start_date, end_date) for location in locations]
        results = await asyncio.gather(*tasks)

    # Flatten the per-location forecast output into a single list for the trip state.
    weather_days = [day for location_days in results for day in location_days]
    state["weather"] = weather_days
    if weather_days:
        state["weather_status"] = "success"
        state["weather_message"] = ""
    else:
        state["weather_status"] = "unavailable"
        state["weather_message"] = "No weather data available for the selected dates."
    return state
