from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator


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


class VehicleDetails(BaseModel):
    vehicle_type: Literal["bike", "car", "suv", "bus"] = "car"
    vehicle_name: str = "Unknown Vehicle"
    fuel_type: Literal["petrol", "diesel", "electric", "cng"] = "petrol"
    mileage_kmpl: float = 15.0
    tank_capacity_litres: float | None = None
    number_of_people: int = 1

    @field_validator("vehicle_type", "fuel_type", mode="before")
    @classmethod
    def _normalize_choice(cls, value: str) -> str:
        value = str(value).strip()
        if not value:
            raise ValueError("This field cannot be empty.")
        normalized = value.lower()
        return "bus" if normalized == "truck" else normalized

    @field_validator("vehicle_name")
    @classmethod
    def _strip_vehicle_name(cls, value: str) -> str:
        value = str(value).strip()
        if not value:
            raise ValueError("This field cannot be empty.")
        return value

    @field_validator("mileage_kmpl")
    @classmethod
    def _validate_mileage(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("mileage_kmpl must be greater than zero.")
        return value

    @field_validator("tank_capacity_litres")
    @classmethod
    def _validate_tank_capacity(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("tank_capacity_litres must be greater than zero when provided.")
        return value

    @field_validator("number_of_people")
    @classmethod
    def _validate_people_count(cls, value: int, info: ValidationInfo) -> int:
        if value <= 0:
            raise ValueError("number_of_people must be at least 1.")
        vehicle_type = str(info.data.get("vehicle_type") or "car").lower()
        max_people = 50 if vehicle_type == "bus" else 10
        if value > max_people:
            raise ValueError(f"number_of_people must be at most {max_people} for {vehicle_type}.")
        return value


class FuelCalculation(BaseModel):
    distance_km: float
    mileage_kmpl: float
    fuel_required_litres: float
    fuel_type: str
    fuel_price_per_litre: float
    total_fuel_cost_inr: float
    total_fuel_cost_usd: float
    refueling_stops: int
    cost_per_person_inr: float
    vehicle_name: str
    vehicle_type: str


class TripRequest(BaseModel):
    origin: str
    destination: str
    dates: str | None = None
    travel_dates: TravelDates | None = None
    trip_days: int = 1
    budget: float
    preferences: list[str] = Field(default_factory=list)
    user_id: str = "guest"
    waypoints: list[str] = Field(default_factory=list)
    vehicle: VehicleDetails = Field(default_factory=VehicleDetails)

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
        if self.trip_days < 1:
            raise ValueError("trip_days must be at least 1.")
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


class HotelRecommendation(BaseModel):
    place_id: str
    name: str
    description: str
    address: str
    rating: float
    total_reviews: int
    price_range: str
    price_level: int
    photo_url: Optional[str] = None
    lat: float
    lng: float
    maps_url: str
    website: Optional[str] = None
    phone: Optional[str] = None
    open_now: Optional[bool] = None
    category: str
    estimated_cost_inr: Optional[float] = None


class RestaurantRecommendation(BaseModel):
    place_id: str
    name: str
    description: str
    address: str
    rating: float
    total_reviews: int
    price_range: str
    price_level: int
    photo_url: Optional[str] = None
    lat: float
    lng: float
    maps_url: str
    website: Optional[str] = None
    phone: Optional[str] = None
    open_now: Optional[bool] = None
    cuisine: str
    category: str = "Both"
    estimated_cost_inr: Optional[float] = None


class AttractionRecommendation(BaseModel):
    place_id: str
    name: str
    description: str
    address: str
    rating: float
    total_reviews: int
    entry_fee: str
    price_level: int
    photo_url: Optional[str] = None
    lat: float
    lng: float
    maps_url: str
    website: Optional[str] = None
    phone: Optional[str] = None
    open_now: Optional[bool] = None
    type: str
    entry_fee_inr: Optional[float] = None


class LocationRecommendation(BaseModel):
    location: str
    hotels: list[HotelRecommendation] = Field(default_factory=list)
    restaurants: list[RestaurantRecommendation] = Field(default_factory=list)
    attractions: list[AttractionRecommendation] = Field(default_factory=list)
    no_results: dict[str, bool] = Field(default_factory=dict)


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
    recommendations: list[LocationRecommendation] = Field(default_factory=list)
    recommendation_locations: list[str] = Field(default_factory=list)
    report_summary: str = ""
    pdf_path: str | None = None
    vehicle: VehicleDetails | None = None
    fuel_calculation: FuelCalculation | None = None
    fuel_cost_inr: float | None = None
    toll_cost_inr: float | None = None
    hotel_cost_inr: float | None = None
    hotel_price_per_night: float | None = None
    hotel_category: str | None = None
    hotel_nights: int | None = None
    hotel_daily_breakdown: list[dict[str, Any]] = Field(default_factory=list)
    hotel_explanation: str | None = None
    food_cost_inr: float | None = None
    food_price_per_day_per_person: float | None = None
    food_type: str | None = None
    food_days: int | None = None
    food_is_vegetarian: bool | None = None
    food_daily_breakdown: list[dict[str, Any]] = Field(default_factory=list)
    food_explanation: str | None = None
    misc_cost_inr: float | None = None
    number_of_people: int | None = None
    trip_days: int | None = None
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
    recommendations: list[LocationRecommendation] = Field(default_factory=list)
    recommendation_locations: list[str] = Field(default_factory=list)


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
