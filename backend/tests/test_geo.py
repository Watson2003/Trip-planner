from __future__ import annotations

import unittest

from utils.geo import cluster_nearby_places, haversine_distance_km


class GeoUtilsTest(unittest.TestCase):
    def test_haversine_distance_km(self) -> None:
        distance = haversine_distance_km(11.4102, 76.6950, 11.4120, 76.7040)
        self.assertGreater(distance, 0.0)
        self.assertLess(distance, 2.0)

    def test_cluster_nearby_places_groups_close_places(self) -> None:
        places = [
            {"name": "A", "latitude": 11.4102, "longitude": 76.6950},
            {"name": "B", "latitude": 11.4110, "longitude": 76.6960},
            {"name": "Far", "latitude": 11.55, "longitude": 76.9},
        ]
        clusters = cluster_nearby_places(places, max_distance_km=2)
        self.assertEqual(len(clusters), 2)
        self.assertEqual(len(clusters[0]["places"]), 2)
        self.assertEqual(len(clusters[1]["places"]), 1)


if __name__ == "__main__":
    unittest.main()
