from __future__ import annotations

from models.schemas import FuelCalculation


# Fuel prices are kept hardcoded so the backend stays functional even when
# a live price feed is not available. Update these periodically.
FUEL_PRICES_INR: dict[str, float] = {
    "petrol": 106.0,
    "diesel": 95.0,
    "cng": 85.0,
    "electric": 9.0,
}

CITY_FUEL_PRICES_INR: dict[str, dict[str, float]] = {
    "mumbai": {"petrol": 106.31, "diesel": 92.15},
    "delhi": {"petrol": 94.77, "diesel": 87.67},
    "chennai": {"petrol": 100.75, "diesel": 90.34},
    "bangalore": {"petrol": 101.94, "diesel": 87.89},
    "bengaluru": {"petrol": 101.94, "diesel": 87.89},
    "hyderabad": {"petrol": 107.41, "diesel": 95.65},
    "kolkata": {"petrol": 104.95, "diesel": 91.76},
}

USD_PER_INR = 1 / 83.5


def _normalize(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def get_fuel_price(fuel_type: str, city: str = "") -> float:
    """Return the current price for a fuel type, using city data when available."""
    normalized_fuel = _normalize(fuel_type)
    if normalized_fuel not in FUEL_PRICES_INR:
        normalized_fuel = "petrol"

    normalized_city = _normalize(city)
    if normalized_city:
        for city_key, prices in CITY_FUEL_PRICES_INR.items():
            if city_key == normalized_city or city_key in normalized_city or normalized_city in city_key:
                if normalized_fuel in prices:
                    return prices[normalized_fuel]

    return FUEL_PRICES_INR[normalized_fuel]


def calculate_fuel_cost(
    *,
    distance_km: float,
    mileage_kmpl: float,
    fuel_type: str,
    tank_capacity: float | None,
    number_of_people: int,
    origin_city: str,
    vehicle_name: str,
    vehicle_type: str,
) -> FuelCalculation:
    """Build a detailed fuel-cost summary for the selected vehicle."""
    mileage = mileage_kmpl if mileage_kmpl > 0 else 1.0
    people = max(1, int(number_of_people or 1))
    fuel_required = max(0.0, float(distance_km or 0.0) / mileage)
    fuel_price = get_fuel_price(fuel_type, origin_city)
    total_cost_inr = fuel_required * fuel_price
    total_cost_usd = total_cost_inr * USD_PER_INR
    refueling_stops = int(fuel_required / tank_capacity) if tank_capacity and tank_capacity > 0 else 0
    cost_per_person = total_cost_inr / people if people else total_cost_inr

    return FuelCalculation(
        distance_km=round(float(distance_km or 0.0), 2),
        mileage_kmpl=round(float(mileage), 2),
        fuel_required_litres=round(fuel_required, 2),
        fuel_type=_normalize(fuel_type) or "petrol",
        fuel_price_per_litre=round(fuel_price, 2),
        total_fuel_cost_inr=round(total_cost_inr, 2),
        total_fuel_cost_usd=round(total_cost_usd, 2),
        refueling_stops=refueling_stops,
        cost_per_person_inr=round(cost_per_person, 2),
        vehicle_name=vehicle_name or "Unknown Vehicle",
        vehicle_type=vehicle_type or "car",
    )
