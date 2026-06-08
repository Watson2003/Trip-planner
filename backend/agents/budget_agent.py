from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from agents.state import TripState
from utils.fuel_price import calculate_fuel_cost


USD_TO_INR = 83.5

DESTINATION_HOTEL_PRICES: dict[str, dict[str, int]] = {
    "ooty": {"budget": 800, "mid": 1800, "luxury": 4500},
    "kodaikanal": {"budget": 700, "mid": 1500, "luxury": 4000},
    "munnar": {"budget": 900, "mid": 2000, "luxury": 5000},
    "coorg": {"budget": 1000, "mid": 2500, "luxury": 6000},
    "wayanad": {"budget": 900, "mid": 2200, "luxury": 5500},
    "yercaud": {"budget": 600, "mid": 1200, "luxury": 3000},
    "valparai": {"budget": 600, "mid": 1200, "luxury": 3000},
    "goa": {"budget": 1200, "mid": 3000, "luxury": 8000},
    "pondicherry": {"budget": 800, "mid": 2000, "luxury": 5000},
    "varkala": {"budget": 700, "mid": 1800, "luxury": 4500},
    "alleppey": {"budget": 900, "mid": 2500, "luxury": 7000},
    "mahabalipuram": {"budget": 700, "mid": 1500, "luxury": 4000},
    "rameswaram": {"budget": 500, "mid": 1000, "luxury": 2500},
    "kanyakumari": {"budget": 600, "mid": 1200, "luxury": 3000},
    "manali": {"budget": 800, "mid": 2000, "luxury": 6000},
    "shimla": {"budget": 900, "mid": 2200, "luxury": 6500},
    "mussoorie": {"budget": 1000, "mid": 2500, "luxury": 7000},
    "nainital": {"budget": 900, "mid": 2000, "luxury": 5500},
    "rishikesh": {"budget": 600, "mid": 1500, "luxury": 4000},
    "haridwar": {"budget": 500, "mid": 1200, "luxury": 3000},
    "darjeeling": {"budget": 700, "mid": 1800, "luxury": 5000},
    "leh": {"budget": 1000, "mid": 2500, "luxury": 7000},
    "hampi": {"budget": 500, "mid": 1200, "luxury": 3500},
    "varanasi": {"budget": 600, "mid": 1500, "luxury": 4000},
    "agra": {"budget": 700, "mid": 1800, "luxury": 5000},
    "jaipur": {"budget": 800, "mid": 2000, "luxury": 6000},
    "udaipur": {"budget": 900, "mid": 2500, "luxury": 8000},
    "pushkar": {"budget": 500, "mid": 1200, "luxury": 3500},
    "mysore": {"budget": 700, "mid": 1800, "luxury": 5000},
    "mysuru": {"budget": 700, "mid": 1800, "luxury": 5000},
    "madurai": {"budget": 600, "mid": 1400, "luxury": 3500},
    "chennai": {"budget": 1200, "mid": 2800, "luxury": 7000},
    "bangalore": {"budget": 1500, "mid": 3500, "luxury": 9000},
    "bengaluru": {"budget": 1500, "mid": 3500, "luxury": 9000},
    "mumbai": {"budget": 1800, "mid": 4000, "luxury": 12000},
    "delhi": {"budget": 1500, "mid": 3500, "luxury": 10000},
    "hyderabad": {"budget": 1200, "mid": 2800, "luxury": 7500},
    "pune": {"budget": 1200, "mid": 2800, "luxury": 7000},
    "kolkata": {"budget": 1000, "mid": 2500, "luxury": 7000},
    "ahmedabad": {"budget": 900, "mid": 2200, "luxury": 6000},
    "trichy": {"budget": 600, "mid": 1400, "luxury": 3500},
    "tiruchirappalli": {"budget": 600, "mid": 1400, "luxury": 3500},
    "coimbatore": {"budget": 700, "mid": 1600, "luxury": 4000},
    "salem": {"budget": 500, "mid": 1200, "luxury": 3000},
    "tirunelveli": {"budget": 500, "mid": 1100, "luxury": 2800},
    "thanjavur": {"budget": 500, "mid": 1100, "luxury": 2800},
    "vellore": {"budget": 500, "mid": 1100, "luxury": 2800},
}

DESTINATION_FOOD_PRICES: dict[str, dict[str, int]] = {
    "ooty": {"veg": 300, "nonveg": 420},
    "kodaikanal": {"veg": 280, "nonveg": 400},
    "munnar": {"veg": 320, "nonveg": 450},
    "coorg": {"veg": 350, "nonveg": 500},
    "wayanad": {"veg": 300, "nonveg": 450},
    "yercaud": {"veg": 250, "nonveg": 350},
    "valparai": {"veg": 230, "nonveg": 320},
    "goa": {"veg": 500, "nonveg": 750},
    "pondicherry": {"veg": 400, "nonveg": 600},
    "varkala": {"veg": 380, "nonveg": 550},
    "alleppey": {"veg": 350, "nonveg": 520},
    "mahabalipuram": {"veg": 350, "nonveg": 500},
    "rameswaram": {"veg": 200, "nonveg": 280},
    "kanyakumari": {"veg": 220, "nonveg": 300},
    "manali": {"veg": 400, "nonveg": 580},
    "shimla": {"veg": 380, "nonveg": 550},
    "mussoorie": {"veg": 400, "nonveg": 580},
    "nainital": {"veg": 380, "nonveg": 530},
    "rishikesh": {"veg": 300, "nonveg": 420},
    "haridwar": {"veg": 250, "nonveg": 350},
    "darjeeling": {"veg": 350, "nonveg": 500},
    "leh": {"veg": 450, "nonveg": 650},
    "hampi": {"veg": 250, "nonveg": 350},
    "varanasi": {"veg": 280, "nonveg": 400},
    "agra": {"veg": 350, "nonveg": 500},
    "jaipur": {"veg": 380, "nonveg": 520},
    "udaipur": {"veg": 400, "nonveg": 580},
    "mysore": {"veg": 300, "nonveg": 420},
    "mysuru": {"veg": 300, "nonveg": 420},
    "madurai": {"veg": 220, "nonveg": 320},
    "chennai": {"veg": 450, "nonveg": 650},
    "bangalore": {"veg": 500, "nonveg": 750},
    "bengaluru": {"veg": 500, "nonveg": 750},
    "mumbai": {"veg": 600, "nonveg": 900},
    "delhi": {"veg": 550, "nonveg": 800},
    "hyderabad": {"veg": 450, "nonveg": 680},
    "pune": {"veg": 450, "nonveg": 650},
    "kolkata": {"veg": 400, "nonveg": 580},
    "trichy": {"veg": 200, "nonveg": 300},
    "tiruchirappalli": {"veg": 200, "nonveg": 300},
    "coimbatore": {"veg": 220, "nonveg": 320},
    "salem": {"veg": 180, "nonveg": 270},
    "tirunelveli": {"veg": 180, "nonveg": 260},
    "thanjavur": {"veg": 180, "nonveg": 260},
}

TOLL_COST_PER_100KM: dict[str, int] = {
    "bike": 0,
    "car": 65,
    "suv": 85,
    "truck": 130,
}


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


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


def _normalize_dates_string(dates_value: Any) -> str:
    if isinstance(dates_value, dict):
        start_value = str(dates_value.get("start") or dates_value.get("start_date") or "").strip()
        end_value = str(dates_value.get("end") or dates_value.get("end_date") or "").strip()
        return f"{start_value} to {end_value}" if start_value and end_value else ""

    start_value = getattr(dates_value, "start", "")
    end_value = getattr(dates_value, "end", "")
    if start_value and end_value:
        return f"{str(start_value).strip()} to {str(end_value).strip()}"

    return str(dates_value or "").strip()


def get_trip_duration(dates_value: Any) -> dict:
    dates_string = _normalize_dates_string(dates_value)
    print(f"DEBUG duration input: '{dates_string}'")

    if not dates_string or " to " not in dates_string:
        print("DEBUG: invalid dates string, using default")
        return {"days": 1, "nights": 1}

    try:
        parts = dates_string.strip().split(" to ")
        start_str = parts[0].strip()
        end_str = parts[1].strip()

        print(f"DEBUG: start_str='{start_str}' end_str='{end_str}'")

        formats_to_try = [
            "%d-%m-%Y",
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%Y/%m/%d",
            "%m-%d-%Y",
            "%d-%b-%Y",
            "%d %b %Y",
            "%B %d %Y",
        ]

        start_date = None
        end_date = None

        for fmt in formats_to_try:
            try:
                start_date = datetime.strptime(start_str, fmt).date()
                end_date = datetime.strptime(end_str, fmt).date()
                print(f"DEBUG: matched format '{fmt}'")
                break
            except ValueError:
                continue

        if not start_date or not end_date:
            print("DEBUG: no format matched, trying numeric detection")
            first_num = int(start_str.split("-")[0])
            if first_num > 12:
                start_date = datetime.strptime(start_str, "%d-%m-%Y").date()
                end_date = datetime.strptime(end_str, "%d-%m-%Y").date()
                print("DEBUG: detected DD-MM-YYYY from first number > 12")
            else:
                print("DEBUG: all formats failed")
                return {"days": 1, "nights": 1}

        if end_date < start_date:
            print("DEBUG: end date before start date, swapping")
            start_date, end_date = end_date, start_date

        delta = (end_date - start_date).days
        days = delta + 1
        nights = max(delta, 1)

        print(f"DEBUG: start={start_date} end={end_date} delta={delta} days={days} nights={nights}")

        return {
            "days": days,
            "nights": nights,
            "start_date": start_date,
            "end_date": end_date,
        }
    except Exception as e:
        print(f"DEBUG get_trip_duration EXCEPTION: {e}")
        import traceback

        traceback.print_exc()
        return {"days": 1, "nights": 1}


def _get_destination_tier(destination: str) -> str:
    dest_lower = destination.lower().strip()
    for tier, cities in DESTINATION_HOTEL_PRICES.items():
        for city in cities:
            if city in dest_lower or dest_lower in city:
                return tier
    return "tier2"


def _get_city_price_map(destination: str, database: dict[str, dict[str, int]], fallback: dict[str, int]) -> dict[str, int]:
    dest_lower = destination.lower().strip()
    for city, prices in database.items():
        if city in dest_lower or dest_lower in city:
            return prices
    return fallback


def get_hotel_price_per_night(destination: str, total_budget: float, preferences: list) -> dict[str, Any]:
    price_data = _get_city_price_map(destination, DESTINATION_HOTEL_PRICES, {"budget": 700, "mid": 1800, "luxury": 5000})

    has_budget_pref = any(str(p).lower() in ["budget hotels", "budget"] for p in preferences)

    if has_budget_pref or total_budget <= 8000:
        category = "budget"
    elif total_budget >= 40000:
        category = "luxury"
    else:
        category = "mid"

    price = price_data[category]
    return {"price_per_night": price, "category": category, "destination": destination}


def get_food_price_per_day(destination: str, preferences: list, total_budget: float) -> dict[str, Any]:
    food_data = _get_city_price_map(destination, DESTINATION_FOOD_PRICES, {"veg": 300, "nonveg": 450})

    is_vegetarian = any(str(p).lower() in ["vegetarian", "vegetarian food", "veg"] for p in preferences)
    base_price = food_data["veg"] if is_vegetarian else food_data["nonveg"]

    if total_budget <= 8000:
        multiplier = 0.7
        food_type = "Street food / Local dhabas"
    elif total_budget >= 40000:
        multiplier = 1.5
        food_type = "Restaurants"
    else:
        multiplier = 1.0
        food_type = "Local restaurants"

    final_price = round(base_price * multiplier, 0)
    return {
        "price_per_day_per_person": final_price,
        "food_type": food_type,
        "is_vegetarian": is_vegetarian,
    }


def build_hotel_daily_breakdown(price_per_night: float, number_of_nights: int, dates_string: str) -> list[dict[str, Any]]:
    try:
        parts = dates_string.split(" to ")
        start = datetime.strptime(parts[0].strip(), "%Y-%m-%d").date()

        breakdown: list[dict[str, Any]] = []
        for i in range(number_of_nights):
            night_date = start + timedelta(days=i)
            next_date = start + timedelta(days=i + 1)
            breakdown.append(
                {
                    "night": i + 1,
                    "date": night_date.strftime("%d %b %Y"),
                    "checkout_date": next_date.strftime("%d %b %Y"),
                    "label": f"Night {i + 1}: {night_date.strftime('%d %b')} -> {next_date.strftime('%d %b')}",
                    "cost": round(price_per_night, 2),
                }
            )
        return breakdown
    except Exception:
        return [
            {
                "night": i + 1,
                "date": f"Night {i + 1}",
                "checkout_date": f"Day {i + 2}",
                "label": f"Night {i + 1}",
                "cost": round(price_per_night, 2),
            }
            for i in range(number_of_nights)
        ]


def build_food_daily_breakdown(
    price_per_day_per_person: float,
    number_of_days: int,
    number_of_people: int,
    dates_string: str,
) -> list[dict[str, Any]]:
    try:
        parts = dates_string.split(" to ")
        start = datetime.strptime(parts[0].strip(), "%Y-%m-%d").date()

        breakdown: list[dict[str, Any]] = []
        daily_total = round(price_per_day_per_person * number_of_people, 2)

        for i in range(number_of_days):
            day_date = start + timedelta(days=i)
            breakdown.append(
                {
                    "day": i + 1,
                    "date": day_date.strftime("%d %b %Y"),
                    "label": f"Day {i + 1}: {day_date.strftime('%d %b %Y')}",
                    "cost_per_person": round(price_per_day_per_person, 2),
                    "total_cost": daily_total,
                    "people": number_of_people,
                }
            )
        return breakdown
    except Exception:
        return [
            {
                "day": i + 1,
                "date": f"Day {i + 1}",
                "label": f"Day {i + 1}",
                "cost_per_person": round(price_per_day_per_person, 2),
                "total_cost": round(price_per_day_per_person * number_of_people, 2),
                "people": number_of_people,
            }
            for i in range(number_of_days)
        ]


def calculate_toll_cost(distance_km: float, vehicle_type: str) -> float:
    rate = TOLL_COST_PER_100KM.get(vehicle_type.lower(), 65)
    toll = (distance_km / 100.0) * rate
    return round(toll, 2)


def parse_dates(dates_string: str) -> dict[str, int]:
    default = {"days": 1, "nights": 1}
    try:
        if " to " not in dates_string:
            return default

        start_raw, end_raw = [part.strip() for part in dates_string.split(" to ", 1)]
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                start_date = datetime.strptime(start_raw, fmt).date()
                end_date = datetime.strptime(end_raw, fmt).date()
                delta = (end_date - start_date).days
                return {
                    "days": max(delta + 1, 1),
                    "nights": max(delta, 1),
                }
            except ValueError:
                continue
        return default
    except Exception:
        return default


def run_budget_agent(state: TripState) -> TripState:
    destination = str(state.get("destination") or "Unknown")
    origin = str(state.get("origin") or "")
    total_budget = float(state.get("budget", 15000) or 15000)
    preferences = [str(pref).lower().strip() for pref in state.get("preferences", []) if str(pref).strip()]
    vehicle = _extract_vehicle(state)
    number_of_people = vehicle["number_of_people"]
    distance_km = _route_distance_km(state)
    vehicle_type = vehicle["vehicle_type"]
    dates_value = state.get("dates") or state.get("travel_dates") or ""
    dates_string = _normalize_dates_string(dates_value)

    raw_trip_days = state.get("trip_days", 0)
    try:
        trip_days_input = int(raw_trip_days)
    except (TypeError, ValueError):
        trip_days_input = 0

    print(f"[BUDGET] raw trip_days from state: {raw_trip_days}")
    print(f"[BUDGET] trip_days_input: {trip_days_input}")

    if trip_days_input >= 1:
        number_of_days = trip_days_input
        number_of_nights = max(trip_days_input - 1, 1)
    else:
        parsed = parse_dates(dates_string)
        number_of_days = parsed["days"]
        number_of_nights = parsed["nights"]

    if number_of_nights == 0:
        print("[BUDGET] WARNING: nights=0, forcing to 1")
        number_of_nights = 1
    if number_of_days == 0:
        print("[BUDGET] WARNING: days=0, forcing to 1")
        number_of_days = 1

    print(f"[BUDGET] FINAL days={number_of_days} nights={number_of_nights}")

    fuel_calculation = calculate_fuel_cost(
        distance_km=distance_km,
        mileage_kmpl=vehicle["mileage_kmpl"],
        fuel_type=vehicle["fuel_type"],
        tank_capacity=vehicle["tank_capacity_litres"],
        number_of_people=number_of_people,
        origin_city=origin,
        vehicle_name=vehicle["vehicle_name"],
        vehicle_type=vehicle_type,
    )
    fuel_cost_inr = round(fuel_calculation.total_fuel_cost_inr, 2)

    hotel_info = get_hotel_price_per_night(
        destination=destination,
        total_budget=total_budget,
        preferences=preferences,
    )
    price_per_night = hotel_info["price_per_night"]
    hotel_cost_inr = round(price_per_night * number_of_nights, 2)
    print(f"[BUDGET] Hotel: Rs{price_per_night}/night x {number_of_nights} nights = Rs{hotel_cost_inr}")

    hotel_daily_breakdown = build_hotel_daily_breakdown(
        price_per_night=price_per_night,
        number_of_nights=number_of_nights,
        dates_string=dates_string,
    )
    hotel_explanation = (
        f"Rs{price_per_night:,}/night x "
        f"{number_of_nights} night{'s' if number_of_nights > 1 else ''} "
        f"({hotel_info['category'].title()} hotel in {destination})"
    )

    food_info = get_food_price_per_day(
        destination=destination,
        preferences=preferences,
        total_budget=total_budget,
    )
    price_per_day_per_person = food_info["price_per_day_per_person"]
    food_cost_inr = round(price_per_day_per_person * number_of_people * number_of_days, 2)
    print(
        f"[BUDGET] Food: Rs{price_per_day_per_person}/person/day x "
        f"{number_of_people} people x {number_of_days} days = Rs{food_cost_inr}"
    )

    food_daily_breakdown = build_food_daily_breakdown(
        price_per_day_per_person=price_per_day_per_person,
        number_of_days=number_of_days,
        number_of_people=number_of_people,
        dates_string=dates_string,
    )
    food_explanation = (
        f"Rs{price_per_day_per_person:,}/person/day x "
        f"{number_of_people} person{'s' if number_of_people > 1 else ''} x "
        f"{number_of_days} day{'s' if number_of_days > 1 else ''} "
        f"({'Veg' if food_info['is_vegetarian'] else 'Non-Veg'} - {food_info['food_type']})"
    )

    toll_cost_inr = calculate_toll_cost(distance_km=distance_km, vehicle_type=vehicle_type)
    misc_cost_inr = round(total_budget * 0.05, 2)
    grand_total = round(
        fuel_cost_inr + hotel_cost_inr + food_cost_inr + toll_cost_inr + misc_cost_inr,
        2,
    )
    people = max(number_of_people, 1)
    cost_per_person = round(grand_total / people, 2)
    print(f"[BUDGET] Cost per person: Rs{grand_total} ÷ {people} = Rs{cost_per_person}")

    print("[BUDGET] === FINAL SUMMARY ===")
    print(f"  Fuel:   Rs{fuel_cost_inr}")
    print(f"  Hotel:  Rs{hotel_cost_inr} ({number_of_nights} nights)")
    print(f"  Food:   Rs{food_cost_inr} ({number_of_days} days)")
    print(f"  Toll:   Rs{toll_cost_inr}")
    print(f"  Misc:   Rs{misc_cost_inr}")
    print(f"  TOTAL:  Rs{grand_total}")

    budget_breakdown = {
        "fuel_cost_inr": fuel_cost_inr,
        "hotel_cost_inr": hotel_cost_inr,
        "hotel_price_per_night": price_per_night,
        "hotel_category": hotel_info["category"],
        "hotel_nights": number_of_nights,
        "hotel_daily_breakdown": hotel_daily_breakdown,
        "hotel_explanation": hotel_explanation,
        "food_cost_inr": food_cost_inr,
        "food_price_per_day_per_person": price_per_day_per_person,
        "food_type": food_info["food_type"],
        "food_days": number_of_days,
        "food_is_vegetarian": food_info["is_vegetarian"],
        "food_daily_breakdown": food_daily_breakdown,
        "food_explanation": food_explanation,
        "toll_cost_inr": toll_cost_inr,
        "misc_cost_inr": misc_cost_inr,
        "total_cost_inr": grand_total,
        "total_cost_usd": round(grand_total / USD_TO_INR, 2),
        "cost_per_person_inr": cost_per_person,
        "cost_per_person_usd": round(cost_per_person / USD_TO_INR, 2),
        "number_of_people": number_of_people,
        "trip_days": number_of_days,
        "trip_nights": number_of_nights,
        "destination": destination,
    }

    state["vehicle"] = {
        **vehicle,
        "number_of_people": number_of_people,
    }
    state["fuel_calculation"] = fuel_calculation.model_dump()
    state["fuel_cost_inr"] = fuel_cost_inr
    state["toll_cost_inr"] = round(toll_cost_inr, 2)
    state["hotel_cost_inr"] = hotel_cost_inr
    state["food_cost_inr"] = food_cost_inr
    state["misc_cost_inr"] = round(misc_cost_inr, 2)
    state["miscellaneous_cost_inr"] = round(misc_cost_inr, 2)
    state["number_of_people"] = number_of_people
    state["trip_days"] = number_of_days
    state["cost_per_person_inr"] = cost_per_person
    state["total_inr"] = grand_total
    state["total_usd"] = round(grand_total / USD_TO_INR, 2)
    state["budget_breakdown"] = budget_breakdown
    state["hotel_price_per_night"] = price_per_night
    state["hotel_category"] = hotel_info["category"]
    state["hotel_nights"] = number_of_nights
    state["hotel_daily_breakdown"] = hotel_daily_breakdown
    state["hotel_explanation"] = hotel_explanation
    state["food_price_per_day_per_person"] = price_per_day_per_person
    state["food_type"] = food_info["food_type"]
    state["food_days"] = number_of_days
    state["food_is_vegetarian"] = food_info["is_vegetarian"]
    state["food_daily_breakdown"] = food_daily_breakdown
    state["food_explanation"] = food_explanation
    return state


async def budget_agent(state: TripState) -> TripState:
    return run_budget_agent(state)
