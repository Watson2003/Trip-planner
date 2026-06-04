from __future__ import annotations

from math import ceil
from typing import Any

from agents.fallbacks import classify_location
from agents.state import TripState
from utils.fuel_price import calculate_fuel_cost


USD_TO_INR = 83.5


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


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


def _route_distance_km(state: TripState) -> float:
    route = state.get("route") or {}
    if isinstance(route, dict) and route.get("distance_km") is not None:
        return float(route.get("distance_km") or 0.0)
    return float(state.get("route_distance_km") or 0.0)


def _extract_vehicle(state: TripState) -> dict[str, Any]:
    vehicle = state.get("vehicle") or {}
    if not isinstance(vehicle, dict):
        vehicle = {}

    return {
        "vehicle_type": _normalize_text(vehicle.get("vehicle_type")) or "car",
        "vehicle_name": str(vehicle.get("vehicle_name") or "Unknown Vehicle").strip() or "Unknown Vehicle",
        "fuel_type": _normalize_text(vehicle.get("fuel_type")) or "petrol",
        "mileage_kmpl": float(vehicle.get("mileage_kmpl") or 15.0),
        "tank_capacity_litres": vehicle.get("tank_capacity_litres"),
        "number_of_people": max(1, int(vehicle.get("number_of_people") or 1)),
    }


def _hotel_cost_estimate(
    *,
    destination: str,
    preferences: list[str],
    trip_days: int,
    number_of_people: int,
) -> float:
    # Keep the stay estimate deterministic while still reflecting trip style.
    profile = classify_location(destination)
    base_per_night = {
        "coastal": 2600.0,
        "hill": 3200.0,
        "desert": 2900.0,
        "metro": 3400.0,
        "mixed": 2400.0,
    }.get(profile, 2400.0)

    pref_text = " ".join(preferences)
    if "budget hotels" in pref_text:
        base_per_night *= 0.82
    if "scenic route" in pref_text:
        base_per_night *= 1.08

    room_count = max(1, ceil(number_of_people / 2))
    nights = max(1, trip_days - 1)
    return round(base_per_night * nights * room_count, 2)


def _food_cost_estimate(
    *,
    preferences: list[str],
    trip_days: int,
    number_of_people: int,
) -> float:
    pref_text = " ".join(preferences)
    per_person_per_day = 650.0 if "vegetarian food" in pref_text else 850.0
    return round(per_person_per_day * trip_days * number_of_people, 2)


def _toll_cost_estimate(*, distance_km: float, vehicle_type: str, route_has_tolls: bool) -> float:
    if not route_has_tolls or vehicle_type == "bike":
        return 0.0

    multiplier = {
        "car": 1.0,
        "suv": 1.25,
        "truck": 1.75,
        "bike": 0.0,
    }.get(vehicle_type, 1.0)

    # Longer trips generally incur more tolls, but we keep this as a simple estimate.
    return round(max(250.0, distance_km * 2.25 * multiplier), 2)


def _misc_cost_estimate(*, trip_days: int, number_of_people: int, vehicle_type: str) -> float:
    multiplier = {
        "bike": 0.7,
        "car": 1.0,
        "suv": 1.15,
        "truck": 1.35,
    }.get(vehicle_type, 1.0)
    return round((trip_days * 180.0 + number_of_people * 90.0) * multiplier, 2)


async def budget_agent(state: TripState) -> TripState:
    vehicle = _extract_vehicle(state)
    origin = str(state.get("origin") or "")
    destination = str(state.get("destination") or "")
    preferences = [str(pref).lower() for pref in state.get("preferences", [])]
    distance_km = _route_distance_km(state)
    trip_days = max(1, _trip_days(state))
    number_of_people = vehicle["number_of_people"]
    route_has_tolls = bool(state.get("toll_roads", False))

    fuel_calculation = calculate_fuel_cost(
        distance_km=distance_km,
        mileage_kmpl=vehicle["mileage_kmpl"],
        fuel_type=vehicle["fuel_type"],
        tank_capacity=vehicle["tank_capacity_litres"],
        number_of_people=number_of_people,
        origin_city=origin,
        vehicle_name=vehicle["vehicle_name"],
        vehicle_type=vehicle["vehicle_type"],
    )

    hotel_cost_inr = _hotel_cost_estimate(
        destination=destination,
        preferences=preferences,
        trip_days=trip_days,
        number_of_people=number_of_people,
    )
    food_cost_inr = _food_cost_estimate(
        preferences=preferences,
        trip_days=trip_days,
        number_of_people=number_of_people,
    )
    toll_cost_inr = _toll_cost_estimate(
        distance_km=distance_km,
        vehicle_type=vehicle["vehicle_type"],
        route_has_tolls=route_has_tolls,
    )
    misc_cost_inr = _misc_cost_estimate(
        trip_days=trip_days,
        number_of_people=number_of_people,
        vehicle_type=vehicle["vehicle_type"],
    )

    total_inr = (
        fuel_calculation.total_fuel_cost_inr
        + toll_cost_inr
        + hotel_cost_inr
        + food_cost_inr
        + misc_cost_inr
    )
    total_usd = round(total_inr / USD_TO_INR, 2)

    # Persist both the structured fuel calculation and the legacy budget fields.
    state["vehicle"] = {
        **vehicle,
        "number_of_people": number_of_people,
    }
    state["fuel_calculation"] = fuel_calculation.model_dump()
    state["fuel_cost_inr"] = fuel_calculation.total_fuel_cost_inr
    state["toll_cost_inr"] = round(toll_cost_inr, 2)
    state["hotel_cost_inr"] = round(hotel_cost_inr, 2)
    state["food_cost_inr"] = round(food_cost_inr, 2)
    state["misc_cost_inr"] = round(misc_cost_inr, 2)
    state["miscellaneous_cost_inr"] = round(misc_cost_inr, 2)
    state["number_of_people"] = number_of_people
    state["trip_days"] = trip_days
    state["cost_per_person_inr"] = round(total_inr / number_of_people, 2)
    state["total_inr"] = round(total_inr, 2)
    state["total_usd"] = total_usd
    return state
