from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.destination_explorer_agent import destination_explorer_agent  # noqa: E402
from agents.itinerary_agent import run_itinerary_agent  # noqa: E402
from tools.osm_places import fetch_osm_places  # noqa: E402


async def main() -> None:
    origin = "Trichy"
    destination = "Ooty"
    osm_places = await fetch_osm_places(destination, radius_km=12)
    print(f"[DEBUG] OSM places fetched: {len(osm_places)}")

    state = {
        "origin": origin,
        "destination": destination,
        "dates": "2026-06-18 to 2026-06-20",
        "trip_days": 3,
        "budget": 25000,
        "preferences": ["scenic", "nature", "food"],
        "vehicle": {
            "vehicle_type": "car",
            "vehicle_name": "Family Car",
            "fuel_type": "petrol",
            "mileage_kmpl": 16,
            "number_of_people": 4,
        },
        "waypoints": ["Salem", "Coimbatore"],
        "route": {
            "distance_km": 300.83,
            "duration_hours": 4.65,
            "polyline": [[10.7905, 78.7047], [11.0168, 76.9558], [11.4102, 76.6950]],
        },
        "recommendations": [
            {
                "location": origin,
                "hotels": [],
                "restaurants": [{"name": "Trichy Spice House"}],
                "attractions": [],
            },
            {
                "location": "Salem",
                "hotels": [],
                "restaurants": [{"name": "Salem Highway Kitchen"}],
                "attractions": [],
            },
            {
                "location": destination,
                "hotels": [{"name": "Ooty Central Stay"}],
                "restaurants": [{"name": "Ooty Spice House"}],
                "attractions": [{"name": "Ooty Lake"}],
            },
        ],
        "osm_places": osm_places,
        "weather": [],
    }

    with patch("agents.destination_explorer_agent._call_nvidia_json", return_value=""):
        explorer_state = await destination_explorer_agent(dict(state))

    state["destination_explorer"] = explorer_state["destination_explorer"]
    result = run_itinerary_agent(state)
    itinerary = result["itinerary"]

    print(f"[DEBUG] Top attractions: {len(state['destination_explorer']['top_attractions'])}")
    print(f"[DEBUG] Restaurants: {len(state['destination_explorer']['restaurants'])}")
    print(f"[DEBUG] Hotels: {len(state['destination_explorer']['hotels'])}")
    print(f"[DEBUG] Duplicate validation: itinerary days={len(itinerary['days'])}")
    print()
    for day in itinerary["days"]:
        print(f"DAY {day['day_number']} - {day['day_title']}")
        print(f"  {day['summary']}")
        for slot in day["time_slots"]:
            print(
                f"  {slot['time']:>8} | {slot['type']:<10} | {slot.get('place_name') or slot.get('title')} | "
                f"{slot.get('current_location_before')} -> {slot.get('current_location_after')} | "
                f"{slot.get('travel_time_minutes')}"
            )
        print()


if __name__ == "__main__":
    asyncio.run(main())
