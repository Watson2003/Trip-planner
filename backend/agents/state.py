from __future__ import annotations

from typing import Any, NotRequired, TypedDict


class TripState(TypedDict, total=False):
    user_input: str
    origin: str
    destination: str
    travel_dates: dict[str, str]
    budget: float
    preferences: list[str]
    waypoints: list[str]
    user_id: str
    vehicle: dict[str, Any]

    route: dict[str, Any]
    route_distance_km: float
    route_duration_hours: float
    polyline: list[list[float]]
    toll_roads: bool

    weather: list[dict[str, Any]]

    fuel_calculation: dict[str, Any]
    fuel_cost_inr: float
    toll_cost_inr: float
    hotel_cost_inr: float
    food_cost_inr: float
    misc_cost_inr: float
    miscellaneous_cost_inr: float
    number_of_people: int
    trip_days: int
    cost_per_person_inr: float
    total_inr: float
    total_usd: float

    hotels: list[dict[str, Any]]
    restaurants: list[dict[str, Any]]
    attractions: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]
    recommendation_locations: list[str]
    rag_context: list[dict[str, Any]]
    pdf_path: str
    report_summary: str
    trip_report: dict[str, Any]
    errors: list[str]
