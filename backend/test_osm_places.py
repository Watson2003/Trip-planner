from __future__ import annotations

import asyncio
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.osm_places import fetch_osm_places, normalize_place_name  # noqa: E402


class OSMPlacesIntegrationTest(unittest.TestCase):
    def test_fetch_osm_places_for_ooty_returns_real_places(self) -> None:
        places = asyncio.run(fetch_osm_places("Ooty", radius_km=12))
        if not places:
            self.skipTest("OSM API returned no places for Ooty")

        self.assertGreaterEqual(len(places), 5)
        self.assertTrue(all(place.get("name") for place in places))
        self.assertTrue(all(place.get("latitude") is not None and place.get("longitude") is not None for place in places))

        names = [str(place.get("name", "")) for place in places]
        self.assertTrue(
            any(normalize_place_name("Ooty") in normalize_place_name(name) for name in names),
            msg=f"Unexpected Ooty place list: {names[:10]}",
        )

        categories = Counter(str(place.get("category", "")).casefold() for place in places)
        self.assertGreater(
            sum(categories.get(category, 0) for category in {"attraction", "museum", "viewpoint", "restaurant", "hotel", "guest_house", "resort", "park", "peak", "waterfall", "lake", "historic", "mall"}),
            0,
        )

        print("\n[OSM] Destination: Ooty")
        print(f"[OSM] Places fetched: {len(places)}")
        print(f"[OSM] Category counts: {dict(categories)}")
        print("[OSM] Sample places:")
        for place in places[:12]:
            print(
                f"  - {place.get('name')} | {place.get('category')} | "
                f"{place.get('latitude')}, {place.get('longitude')} | {place.get('address', '')}"
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
