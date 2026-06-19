from __future__ import annotations

import unittest

from tools.osm_places import classify_osm_place, deduplicate_places, normalize_place_name


class OsmPlacesHelperTest(unittest.TestCase):
    def test_normalize_place_name_strips_activity_prefixes(self) -> None:
        self.assertEqual(normalize_place_name(" Visit Ooty Lake "), "ooty lake")
        self.assertEqual(normalize_place_name("Explore  Doddabetta Peak"), "doddabetta peak")
        self.assertEqual(normalize_place_name("Dinner at Earl’s Secret"), "earls secret")
        self.assertEqual(normalize_place_name("Check in at Savoy Ooty"), "savoy ooty")
        self.assertEqual(normalize_place_name("Guest House  Stay at Co Operator Guest House"), "co operator guest house")

    def test_classify_osm_place_uses_osm_tags(self) -> None:
        self.assertEqual(classify_osm_place({"tourism": "museum"}), "museum")
        self.assertEqual(classify_osm_place({"amenity": "restaurant"}), "restaurant")
        self.assertEqual(classify_osm_place({"natural": "lake"}), "lake")
        self.assertEqual(classify_osm_place({"historic": "yes"}), "historic")
        self.assertEqual(classify_osm_place({"shop": "mall"}), "mall")

    def test_deduplicate_places_removes_case_and_coordinate_duplicates(self) -> None:
        places = [
            {"name": "Ooty Lake", "latitude": 11.4, "longitude": 76.7},
            {"name": "visit ooty lake", "latitude": 11.40001, "longitude": 76.70001},
            {"name": "Doddabetta Peak", "latitude": 11.4, "longitude": 76.8},
            {"name": "Doddabetta Peak", "latitude": 11.5, "longitude": 76.9},
        ]

        deduped = deduplicate_places(places)
        self.assertEqual(len(deduped), 2)
        self.assertEqual(deduped[0]["name"], "Ooty Lake")
        self.assertEqual(deduped[1]["name"], "Doddabetta Peak")


if __name__ == "__main__":
    unittest.main()
