from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from agents.weather_agent import fetch_weather_forecast
from models.schemas import DailyWeather

router = APIRouter(tags=["weather"])


class WeatherRangeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    total_days: int | None = None
    weather: list[DailyWeather] = Field(default_factory=list)
    message: str | None = None


def _parse_iso_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[{"loc": ["query", field_name], "msg": "Invalid date format. Use YYYY-MM-DD.", "type": "value_error"}],
        ) from exc


@router.get(
    "/weather/{location}",
    response_model=WeatherRangeResponse,
    response_model_exclude_none=True,
)
async def get_weather(
    location: str,
    start_date: Optional[str] = Query(default=None, description="Travel start date in YYYY-MM-DD format"),
    end_date: Optional[str] = Query(default=None, description="Travel end date in YYYY-MM-DD format"),
) -> WeatherRangeResponse:
    location_name = location.strip() or location

    # If only one date is provided, treat it as an invalid date-range request.
    if bool(start_date) != bool(end_date):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Both start_date and end_date must be provided together.",
        )

    if not start_date and not end_date:
        # Fallback to the legacy 5-day forecast behavior when no travel dates are supplied.
        today = date.today()
        weather = await fetch_weather_forecast(location_name, today, today + timedelta(days=4))
        return WeatherRangeResponse(
            status="success",
            location=location_name,
            total_days=len(weather),
            weather=weather,
        )

    parsed_start = _parse_iso_date(start_date, "start_date")
    parsed_end = _parse_iso_date(end_date, "end_date")

    if parsed_end < parsed_start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="end_date must be the same as or later than start_date.",
        )

    today = date.today()
    if parsed_start < today:
        return WeatherRangeResponse(
            status="past_dates",
            message="These travel dates have already passed.",
            weather=[],
        )

    if parsed_start > today + timedelta(days=5):
        return WeatherRangeResponse(
            status="unavailable",
            message=(
                "Forecast not available yet. OpenWeatherMap provides forecasts up to 5 days ahead. "
                "Check back closer to your travel date."
            ),
            weather=[],
        )

    weather = await fetch_weather_forecast(location_name, parsed_start, parsed_end)
    return WeatherRangeResponse(
        status="success",
        location=location_name,
        start_date=parsed_start.isoformat(),
        end_date=parsed_end.isoformat(),
        total_days=len({item["date"] for item in weather}),
        weather=weather,
    )
