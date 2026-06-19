from __future__ import annotations

import unittest

from agents.itinerary_agent import normalize_place_name, run_itinerary_agent


class ItineraryAgentRouteFlowTest(unittest.TestCase):
    def test_trichy_to_ooty_route_flow(self) -> None:
        state = {
            "origin": "Trichy",
            "destination": "Ooty",
            "dates": "2026-06-18 to 2026-06-20",
            "trip_days": 3,
            "budget": 25000,
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
            "destination_explorer": {
                "top_attractions": [
                    {"name": "Government Botanical Garden", "reason": "Iconic garden", "best_time_to_visit": "Morning", "suggested_duration_minutes": 90, "latitude": 11.4, "longitude": 76.7},
                    {"name": "Ooty Lake", "reason": "Classic lake", "best_time_to_visit": "Evening", "suggested_duration_minutes": 60, "latitude": 11.4, "longitude": 76.7},
                ],
                "hidden_gems": [
                    {"name": "Thread Garden", "reason": "Unique floral craft", "best_time_to_visit": "Late Morning", "suggested_duration_minutes": 45, "latitude": 11.4, "longitude": 76.7},
                ],
                "restaurants": [{"name": "Earls Secret", "reason": "Popular dining spot", "best_time_to_visit": "Lunch", "suggested_duration_minutes": 60, "latitude": 11.4, "longitude": 76.7}],
                "hotels": [{"name": "Savoy Ooty", "reason": "Heritage stay", "best_time_to_visit": "Anytime", "suggested_duration_minutes": 30, "latitude": 11.4, "longitude": 76.7}],
                "evening_places": [{"name": "Charring Cross", "reason": "Evening market walk", "best_time_to_visit": "Evening", "suggested_duration_minutes": 60, "latitude": 11.4, "longitude": 76.7}],
                "rainy_day_places": [],
                "scenic_places": [
                    {"name": "Doddabetta Peak", "reason": "Scenic viewpoint", "best_time_to_visit": "Morning", "suggested_duration_minutes": 90, "latitude": 11.4, "longitude": 76.7},
                    {"name": "Pykara Lake", "reason": "Scenic lake", "best_time_to_visit": "Morning", "suggested_duration_minutes": 90, "latitude": 11.4, "longitude": 76.7},
                    {"name": "Pykara Waterfalls", "reason": "Waterfall stop", "best_time_to_visit": "Morning", "suggested_duration_minutes": 60, "latitude": 11.4, "longitude": 76.7},
                    {"name": "Pine Forest", "reason": "Forest walk", "best_time_to_visit": "Afternoon", "suggested_duration_minutes": 60, "latitude": 11.4, "longitude": 76.7},
                    {"name": "Shooting Point", "reason": "Valley views", "best_time_to_visit": "Afternoon", "suggested_duration_minutes": 60, "latitude": 11.4, "longitude": 76.7},
                    {"name": "Wenlock Downs", "reason": "Grassland views", "best_time_to_visit": "Evening", "suggested_duration_minutes": 60, "latitude": 11.4, "longitude": 76.7},
                ],
            },
            "weather": [],
        }

        result = run_itinerary_agent(state)
        itinerary = result["itinerary"]
        day1 = itinerary["days"][0]
        day1_slots = day1["time_slots"]

        breakfast = day1_slots[0]
        fuel_stop = day1_slots[2]
        lunch_stop = day1_slots[3]
        hotel_checkin = day1_slots[4]
        first_attraction = day1_slots[5]
        dinner = next(slot for slot in day1_slots if slot["type"] == "dinner")

        self.assertEqual(breakfast["type"], "breakfast")
        self.assertIn("Trichy", breakfast["location"])
        self.assertIn("Trichy", breakfast["current_location_before"])
        self.assertIn("Trichy", breakfast["current_location_after"])

        self.assertNotIn("Ooty", fuel_stop["location"])
        self.assertNotIn("Ooty", lunch_stop["location"])
        self.assertNotIn("Ooty", fuel_stop["current_location_before"])
        self.assertNotIn("Ooty", lunch_stop["current_location_before"])

        self.assertEqual(hotel_checkin["type"], "hotel")
        self.assertIn("Ooty", hotel_checkin["location"])
        self.assertIn("Ooty", hotel_checkin["current_location_before"])
        self.assertIn("Ooty", hotel_checkin["current_location_after"])
        self.assertEqual(first_attraction["type"], "attraction")
        self.assertIn("Government Botanical Garden", first_attraction.get("place_name", ""))
        self.assertLessEqual(sum(1 for slot in day1_slots if slot["type"] == "rest"), 1)

        self.assertEqual(dinner["type"], "dinner")
        self.assertIn("Ooty", dinner["location"])
        self.assertTrue(dinner["current_location_before"])
        self.assertTrue(dinner["current_location_after"])

        day2_slots = itinerary["days"][1]["time_slots"]
        day2_places = [slot.get("place_name") or slot.get("title") or "" for slot in day2_slots]
        self.assertGreaterEqual(sum(1 for slot in day2_slots if slot["type"] == "attraction"), 3)
        joined_day2 = " ".join(day2_places)
        self.assertTrue(
            any(name in joined_day2 for name in ("Doddabetta Peak", "Pykara Lake", "Rose Garden")),
            msg=f"Unexpected Day 2 attraction mix: {joined_day2}",
        )
        self.assertIn("Thread Garden", joined_day2)
        self.assertTrue(
            any(name in joined_day2 for name in ("Tea Museum", "Pykara Waterfalls", "Government Museum")),
            msg=f"Unexpected Day 2 attraction mix: {joined_day2}",
        )
        self.assertLessEqual(sum(1 for slot in day2_slots if slot["type"] == "rest"), 1)

        day3_slots = itinerary["days"][2]["time_slots"]
        day3_places = [slot.get("place_name") or slot.get("title") or "" for slot in day3_slots]
        self.assertGreaterEqual(sum(1 for slot in day3_slots if slot["type"] == "attraction"), 3)
        joined_day3 = " ".join(day3_places)
        self.assertTrue(
            any(name in joined_day3 for name in ("Pine Forest", "Shooting Point", "Wenlock Downs", "Avalanche Lake", "Rose Garden", "Ooty Lake", "Tea Museum")),
            msg=f"Unexpected Day 3 attraction mix: {joined_day3}",
        )
        self.assertLessEqual(sum(1 for slot in day3_slots if slot["type"] == "rest"), 1)

        used_places: set[str] = set()
        duplicate_titles: list[str] = []
        for day in itinerary["days"]:
            for slot in day["time_slots"]:
                if slot.get("type") not in {"breakfast", "lunch", "dinner", "attraction", "sightseeing", "fuel"}:
                    continue
                label = slot.get("place_name") or slot.get("title") or slot.get("activity") or ""
                normalized = normalize_place_name(label)
                if not normalized:
                    continue
                if normalized in used_places:
                    duplicate_titles.append(label)
                used_places.add(normalized)

        self.assertEqual(duplicate_titles, [], msg=f"Duplicate itinerary places found: {duplicate_titles}")
        self.assertIn("government botanical garden", used_places)
        self.assertIn("ooty lake", used_places)
        self.assertIn("doddabetta peak", used_places)
        self.assertIn("earls secret", used_places)


if __name__ == "__main__":
    unittest.main()
