from __future__ import annotations

import unittest

from agents.destination_explorer_agent import _classify_buckets, _dedupe_places


class DestinationExplorerAgentTest(unittest.TestCase):
    def test_dedupes_and_filters_low_quality_places(self) -> None:
        places = [
            {"name": "Ooty Lake", "category": "lake", "latitude": 11.4, "longitude": 76.7, "rating": 4.5},
            {"name": "visit Ooty Lake", "category": "lake", "latitude": 11.4001, "longitude": 76.7001, "rating": 4.4},
            {"name": "", "category": "attraction", "latitude": 0.0, "longitude": 0.0},
            {"name": "Government Botanical Garden", "category": "attraction", "latitude": 11.4, "longitude": 76.8, "rating": 4.8},
        ]

        deduped = _dedupe_places(places)
        self.assertEqual(len(deduped), 2)
        self.assertEqual(deduped[0]["name"], "Ooty Lake")
        self.assertEqual(deduped[1]["name"], "Government Botanical Garden")

    def test_classifies_places_into_useful_buckets(self) -> None:
        places = [
            {"name": "Ooty Lake", "category": "lake", "latitude": 11.4, "longitude": 76.7, "reason": "Scenic lake"},
            {"name": "Earl's Secret", "category": "restaurant", "latitude": 11.4, "longitude": 76.8, "reason": "Popular dining spot"},
            {"name": "Savoy Ooty", "category": "hotel", "latitude": 11.41, "longitude": 76.69, "reason": "Heritage stay"},
        ]

        buckets = _classify_buckets(places)
        self.assertGreaterEqual(len(buckets["top_attractions"]), 1)
        self.assertGreaterEqual(len(buckets["restaurants"]), 1)
        self.assertGreaterEqual(len(buckets["hotels"]), 1)


if __name__ == "__main__":
    unittest.main()
