from __future__ import annotations

from typing import Any

from agents.state import TripState


USD_TO_INR = 83.0


async def budget_agent(state: TripState) -> TripState:
    distance_km = float(state.get("route_distance_km", 0.0))
    days = max(1, _trip_days(state))
    nights = max(1, days - 1)
    route_has_tolls = bool(state.get("toll_roads", False))
    preferences = [pref.lower() for pref in state.get("preferences", [])]

    fuel_cost_inr = max(1200.0, distance_km * 10.0)
    toll_cost_inr = 500.0 if route_has_tolls else 0.0
    hotel_cost_per_night_inr = 1800.0 if "budget hotels" in preferences else 2500.0
    food_cost_per_day_inr = 650.0 if "vegetarian food" in preferences else 850.0
    if "scenic route" in preferences:
        hotel_cost_per_night_inr += 200.0

    hotel_cost_inr = hotel_cost_per_night_inr * nights
    food_cost_inr = food_cost_per_day_inr * days
    total_inr = fuel_cost_inr + toll_cost_inr + hotel_cost_inr + food_cost_inr

    state["fuel_cost_inr"] = round(fuel_cost_inr, 2)
    state["toll_cost_inr"] = round(toll_cost_inr, 2)
    state["hotel_cost_inr"] = round(hotel_cost_inr, 2)
    state["food_cost_inr"] = round(food_cost_inr, 2)
    state["total_inr"] = round(total_inr, 2)
    state["total_usd"] = round(total_inr / USD_TO_INR, 2)
    return state


def _trip_days(state: TripState) -> int:
    travel_dates = state.get("travel_dates") or {}
    start = travel_dates.get("start")
    end = travel_dates.get("end")
    if not start or not end:
        return 1
    try:
        from datetime import date

        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
        return max(1, (end_date - start_date).days + 1)
    except Exception:
        return 1
