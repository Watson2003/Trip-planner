from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.destination_explorer_agent import destination_explorer_agent  # noqa: E402
from agents.itinerary_agent import normalize_place_name, run_itinerary_agent  # noqa: E402
from tools.osm_places import fetch_osm_places  # noqa: E402


def _build_state(osm_places: list[dict[str, object]]) -> dict[str, object]:
    return {
        "origin": "Trichy",
        "destination": "Ooty",
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
                "location": "Trichy",
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
                "location": "Ooty",
                "hotels": [{"name": "Ooty Central Stay"}],
                "restaurants": [{"name": "Ooty Spice House"}],
                "attractions": [{"name": "Ooty Lake"}],
            },
        ],
        "osm_places": osm_places,
        "weather": [],
    }


class DestinationItineraryIntegrationTest(unittest.TestCase):
    def test_destination_explorer_and_itinerary_flow(self) -> None:
        osm_places = asyncio.run(fetch_osm_places("Ooty", radius_km=12))
        if not osm_places:
            self.skipTest("OSM API returned no places for Ooty")

        state = _build_state(osm_places)

        with patch("agents.destination_explorer_agent._call_nvidia_json", return_value=""):
            explorer_state = asyncio.run(destination_explorer_agent(dict(state)))

        self.assertIn("destination_explorer", explorer_state)
        explorer = explorer_state["destination_explorer"]
        self.assertTrue(explorer["top_attractions"])
        self.assertTrue(explorer["restaurants"])
        self.assertTrue(explorer["hotels"])

        state["destination_explorer"] = explorer
        result = run_itinerary_agent(state)
        itinerary = result["itinerary"]
        days = itinerary["days"]

        full_days = [day for day in days if day["day_title"].startswith("Destination Exploration")]
        self.assertGreaterEqual(len(full_days), 1)
        self.assertGreaterEqual(sum(1 for slot in full_days[0]["time_slots"] if slot["type"] == "attraction"), 3)

        all_places: list[str] = []
        attraction_places: list[str] = []
        hotel_places: list[str] = []
        destination_entries_before_arrival: list[str] = []

        for day in days:
            hotel_index = next((index for index, slot in enumerate(day["time_slots"]) if slot["type"] == "hotel"), None)
            for index, slot in enumerate(day["time_slots"]):
                slot_type = slot["type"]
                place_name = str(slot.get("place_name") or slot.get("title") or slot.get("activity") or "").strip()
                normalized = normalize_place_name(place_name)
                if not normalized:
                    continue

                if slot_type in {"breakfast", "lunch", "dinner", "attraction", "sightseeing", "hotel", "fuel"}:
                    all_places.append(normalized)

                if slot_type in {"attraction", "sightseeing"}:
                    attraction_places.append(normalized)
                    if slot.get("latitude") is not None and slot.get("longitude") is not None:
                        self.assertNotEqual(slot.get("latitude"), 0)
                        self.assertNotEqual(slot.get("longitude"), 0)

                if slot_type == "hotel":
                    hotel_places.append(normalized)

                if day["day_number"] == 1 and hotel_index is not None and index < hotel_index and slot_type in {"attraction", "sightseeing"}:
                    destination_entries_before_arrival.append(place_name)

                if slot_type in {"lunch", "dinner"}:
                    self.assertNotIn(normalized, hotel_places)

        self.assertEqual(len(all_places), len(set(all_places)), msg=f"Duplicate itinerary places found: {all_places}")
        self.assertFalse(destination_entries_before_arrival, msg=f"Destination places shown before arrival: {destination_entries_before_arrival}")
        self.assertTrue(attraction_places, "Expected attraction slots in the itinerary")
        self.assertTrue(hotel_places, "Expected at least one hotel slot in the itinerary")

        print("\n[DESTINATION EXPLORER]")
        print(f"OSM places fetched: {len(osm_places)}")
        print(f"Top attractions: {len(explorer['top_attractions'])}")
        print(f"Restaurants: {len(explorer['restaurants'])}")
        print(f"Hotels: {len(explorer['hotels'])}")
        print("\n[ITINERARY]")
        for day in days:
            print(f"Day {day['day_number']}: {day['day_title']}")
            for slot in day["time_slots"]:
                print(
                    f"  {slot['time']} | {slot['type']} | {slot.get('place_name') or slot.get('title')} | "
                    f"{slot.get('current_location_before')} -> {slot.get('current_location_after')}"
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
