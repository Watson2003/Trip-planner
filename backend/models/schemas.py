from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TripCreate(BaseModel):
    user_id: str
    origin: str
    destination: str
    waypoints: list[Any] = Field(default_factory=list)


class TripRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    origin: str
    destination: str
    waypoints: list[Any]
    created_at: datetime


class TripReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trip_id: int
    pdf_path: str
    created_at: datetime


class TravelDates(BaseModel):
    start: str
    end: str


class TripSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    origin: str
    destination: str
    dates: TravelDates | None = None
    budget: float | None = None
    created_at: datetime


class TripRequest(BaseModel):
    origin: str
    destination: str
    dates: str | None = None
    travel_dates: TravelDates | None = None
    budget: float
    preferences: list[str] = Field(default_factory=list)
    user_id: str = "guest"
    waypoints: list[str] = Field(default_factory=list)

    @field_validator("origin", "destination", "user_id")
    @classmethod
    def _strip_text_fields(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be empty.")
        return value

    @model_validator(mode="after")
    def _validate_trip(self) -> "TripRequest":
        if self.origin.casefold() == self.destination.casefold():
            raise ValueError("Origin and destination must be different.")
        if not self.dates and not self.travel_dates:
            raise ValueError("Travel dates are required.")
        if self.dates and not self.travel_dates:
            try:
                start, end = [part.strip() for part in self.dates.split("to", maxsplit=1)]
            except ValueError as exc:
                raise ValueError("dates must be in the format 'YYYY-MM-DD to YYYY-MM-DD'.") from exc
            try:
                datetime.strptime(start, "%Y-%m-%d")
                datetime.strptime(end, "%Y-%m-%d")
            except ValueError as exc:
                raise ValueError("dates must be in the format 'YYYY-MM-DD to YYYY-MM-DD'.") from exc
            self.travel_dates = TravelDates(start=start, end=end)
        elif self.travel_dates and not self.dates:
            self.dates = f"{self.travel_dates.start} to {self.travel_dates.end}"
        elif self.dates and self.travel_dates:
            self.dates = f"{self.travel_dates.start} to {self.travel_dates.end}"
        return self


class TripPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    trip_id: int
    report_id: int | None = None
    user_id: str
    origin: str
    destination: str
    travel_dates: TravelDates
    budget: float
    preferences: list[str]
    waypoints: list[str]
    route: dict[str, Any] = Field(default_factory=dict)
    weather: list[dict[str, Any]] = Field(default_factory=list)
    weather_status: str = "success"
    weather_message: str | None = None
    recommendations: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    report_summary: str = ""
    pdf_path: str | None = None
    fuel_cost_inr: float | None = None
    toll_cost_inr: float | None = None
    hotel_cost_inr: float | None = None
    food_cost_inr: float | None = None
    total_inr: float | None = None
    total_usd: float | None = None
    created_at: datetime | None = None


class TripDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    origin: str
    destination: str
    waypoints: list[Any]
    created_at: datetime
    pdf_path: str | None = None


class DailyWeather(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: str
    day_name: str
    location: str
    temp_min_celsius: float
    temp_max_celsius: float
    temp_feels_like: float
    humidity_percent: int
    condition: str
    weather_icon: str
    wind_speed_kmh: float
    rain_chance_percent: int
    alert: Optional[str] = None


class WeatherDayResponse(BaseModel):
    location: str
    date: str
    temp_celsius: dict[str, float]
    condition: str
    alert: str | None = None
    entries: list[dict[str, Any]]


class WeatherForecastResponse(BaseModel):
    location: str
    days: list[WeatherDayResponse]


class GeoJsonRouteResponse(BaseModel):
    type: str
    features: list[dict[str, Any]]


class ChatWebSocketRequest(BaseModel):
    session_id: str
    message: str
    trip_context: dict[str, Any] = Field(default_factory=dict)


class ChatStreamEnvelope(BaseModel):
    type: str
    content: str | None = None
    session_id: str | None = None
