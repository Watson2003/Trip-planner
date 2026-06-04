from datetime import datetime
from typing import Any

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
    travel_dates: TravelDates
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
