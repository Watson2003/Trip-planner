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

    route_distance_km: float
    route_duration_hours: float
    polyline: list[list[float]]
    toll_roads: bool

    weather: list[dict[str, Any]]

    fuel_cost_inr: float
    toll_cost_inr: float
    hotel_cost_inr: float
    food_cost_inr: float
    total_inr: float
    total_usd: float

    hotels: list[dict[str, Any]]
    restaurants: list[dict[str, Any]]
    attractions: list[dict[str, Any]]
    rag_context: list[dict[str, Any]]
    pdf_path: str
    report_summary: str
    trip_report: dict[str, Any]
    errors: list[str]
