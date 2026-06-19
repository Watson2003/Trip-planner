from __future__ import annotations

import asyncio
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.osm_places import fetch_osm_places  # noqa: E402


async def main() -> None:
    destination = "Ooty"
    places = await fetch_osm_places(destination, radius_km=12)
    print(f"[OSM DEBUG] destination={destination}")
    print(f"[OSM DEBUG] fetched={len(places)}")
    print(f"[OSM DEBUG] categories={dict(Counter(str(place.get('category', '')).casefold() for place in places))}")
    for index, place in enumerate(places[:20], start=1):
        print(
            f"{index:02d}. {place.get('name')} | {place.get('category')} | "
            f"{place.get('latitude')}, {place.get('longitude')} | {place.get('address', '')}"
        )


if __name__ == "__main__":
    asyncio.run(main())
