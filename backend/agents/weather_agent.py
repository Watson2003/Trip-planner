from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Mapping
from datetime import date, datetime, time, timedelta
from typing import Any

from agents.fallbacks import fallback_daily_weather
from agents.state import TripState
from models.schemas import DailyWeather
from utils.mcp_bridge import mcp_get_weather


logger = logging.getLogger(__name__)

OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/forecast"
TRAVEL_DATES_PATTERN = re.compile(
    r"^\s*(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})\s*$",
    re.IGNORECASE,
)

LOCATION_QUERY_ALIASES: dict[str, list[str]] = {
    "bangalore": ["Bengaluru", "Bangalore, Karnataka, IN"],
    "bengaluru": ["Bangalore", "Bengaluru, Karnataka, IN"],
    "kodaikanal": ["Kodaikanal, Tamil Nadu, IN"],
}


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


def _normalize_location_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).strip().lower()).strip()


def _location_queries(location: str) -> list[str]:
    queries = [str(location).strip()]
    normalized = _normalize_location_key(location)
    for alias in LOCATION_QUERY_ALIASES.get(normalized, []):
        if alias not in queries:
            queries.append(alias)
    return queries


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


def _weather_main_from_description(description: str) -> str:
    lowered = (description or "").strip().lower()
    if any(term in lowered for term in ["thunder", "storm"]):
        return "thunderstorm"
    if "drizzle" in lowered:
        return "drizzle"
    if "rain" in lowered:
        return "rain"
    if any(term in lowered for term in ["snow", "hail"]):
        return "snow"
    if "clear" in lowered:
        return "clear"
    if any(term in lowered for term in ["cloud", "overcast", "scattered", "broken"]):
        return "clouds"
    if any(term in lowered for term in ["mist", "fog", "haze"]):
        return "mist"
    return description


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


def _build_daily_weather_from_mcp(location: str, target_day: date, forecast_day: dict[str, Any]) -> DailyWeather:
    temp_info = forecast_day.get("temp_celsius") or {}
    if not isinstance(temp_info, Mapping):
        temp_info = {}

    entries = forecast_day.get("entries") or []
    if not isinstance(entries, list):
        entries = []

    temperatures = [float(entry.get("temp_celsius", 0.0)) for entry in entries if isinstance(entry, dict)]
    humidity_values = [int(round(float(entry.get("humidity", 0)))) for entry in entries if isinstance(entry, dict)]
    wind_speeds = [float(entry.get("wind_speed", 0.0)) for entry in entries if isinstance(entry, dict)]
    condition = str(forecast_day.get("condition") or "Unknown")
    if not condition and entries:
        condition = str((entries[0] or {}).get("condition") or "Unknown")

    temp_min_celsius = round(float(temp_info.get("min", min(temperatures) if temperatures else 0.0)), 1)
    temp_max_celsius = round(float(temp_info.get("max", max(temperatures) if temperatures else 0.0)), 1)
    temp_feels_like = round(float(temp_info.get("avg", sum(temperatures) / len(temperatures) if temperatures else temp_max_celsius)), 1)
    humidity = int(round(sum(humidity_values) / len(humidity_values))) if humidity_values else 0
    wind_speed_kmh = round((max(wind_speeds) if wind_speeds else 0.0) * 3.6, 1)
    alert = _build_alert(temp_max_celsius=temp_max_celsius, wind_speed_kmh=wind_speed_kmh, rain_chance_percent=0)

    return DailyWeather(
        date=target_day.isoformat(),
        day_name=target_day.strftime("%A"),
        location=location,
        temp_min_celsius=temp_min_celsius,
        temp_max_celsius=temp_max_celsius,
        temp_feels_like=temp_feels_like,
        humidity_percent=humidity,
        condition=condition,
        weather_icon=_weather_icon(_weather_main_from_description(condition), condition),
        wind_speed_kmh=wind_speed_kmh,
        rain_chance_percent=0,
        alert=alert,
    )


def _filter_mcp_forecast_by_date_range(
    payload: dict[str, Any],
    location: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    days = payload.get("days") or []
    if not isinstance(days, list):
        return []

    weather_days: list[dict[str, Any]] = []
    for forecast_day in days:
        if not isinstance(forecast_day, dict):
            continue
        date_value = str(forecast_day.get("date") or "").strip()
        if not date_value:
            continue
        try:
            forecast_date = datetime.strptime(date_value, "%Y-%m-%d").date()
        except ValueError:
            continue
        if not (start_date <= forecast_date <= end_date):
            continue

        daily_weather = _build_daily_weather_from_mcp(location, forecast_date, forecast_day)
        daily_payload = daily_weather.model_dump()
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


async def _fetch_location_weather(location: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
    last_error: Exception | None = None
    for query in _location_queries(location):
        try:
            payload = await asyncio.wait_for(mcp_get_weather(location=query, days=5), timeout=5.0)
            weather_days = _filter_mcp_forecast_by_date_range(payload, location, start_date, end_date)
            if weather_days:
                return weather_days
        except Exception as exc:  # noqa: BLE001 - keep weather fallback resilient
            last_error = exc
            logger.warning("Weather lookup failed for %s using query %s: %s", location, query, exc)

    if last_error is not None:
        logger.exception("Failed to fetch weather forecast for %s after trying aliases", location, exc_info=last_error)
    return []


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
    tasks = [_fetch_location_weather(location, start_date, end_date) for location in locations]
    results = await asyncio.gather(*tasks)

    # Flatten the per-location forecast output into a single list for the trip state.
    weather_days = [day for location_days in results for day in location_days]
    if weather_days:
        state["weather"] = weather_days
        state["weather_status"] = "success"
        state["weather_message"] = ""
    else:
        primary_location = state.get("destination") or state.get("origin") or "Destination"
        state["weather"] = fallback_daily_weather(primary_location, days=max(1, (end_date - start_date).days + 1), start_date=start_date)
        state["weather_status"] = "success"
        state["weather_message"] = ""
    return state
