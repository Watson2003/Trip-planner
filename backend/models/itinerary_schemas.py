from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ActivityCategory(str, Enum):
    DRIVE = "drive"
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    ATTRACTION = "attraction"
    SIGHTSEEING = "sightseeing"
    HOTEL = "hotel"
    SHOPPING = "shopping"
    REST = "rest"
    FUEL = "fuel"
    MISC = "misc"


class TimeSlot(BaseModel):
    time: str
    type: ActivityCategory
    title: str
    place_name: Optional[str] = ""
    location: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    estimated_duration_minutes: int
    cost_inr: float
    reason: str
    best_time_to_visit: Optional[str] = ""
    cluster: Optional[str] = ""
    nearby_places: list[str] = Field(default_factory=list)
    travel_time_minutes: Optional[int] = None
    distance_from_previous_km: Optional[float] = None
    route_progress_percent: Optional[float] = None
    is_destination_activity: bool = False
    requires_arrival: bool = False
    current_location_before: str
    current_location_after: str
    activity: Optional[str] = ""
    description: Optional[str] = ""
    duration_minutes: Optional[int] = None
    category: Optional[ActivityCategory] = None
    estimated_cost_inr: Optional[float] = None
    tips: Optional[str] = ""


class DayItinerary(BaseModel):
    day_number: int
    date: str
    day_title: str
    summary: str
    location: str
    time_slots: list[TimeSlot]
    day_total_cost_inr: float
    distance_km: Optional[float] = 0
    driving_hours: Optional[float] = 0
    highlights: list[str] = Field(default_factory=list)


class FullItinerary(BaseModel):
    trip_id: str
    origin: str
    destination: str
    total_days: int
    start_date: str
    end_date: str
    days: list[DayItinerary]
    total_itinerary_cost_inr: float
    generated_at: str
    travel_tips: list[str] = Field(default_factory=list)
