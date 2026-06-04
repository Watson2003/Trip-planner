from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


# Allow direct execution via `python rag/seed_data.py` from the backend folder.
if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from rag.setup import get_collection, get_embeddings


@dataclass(frozen=True)
class SeedChunk:
    destination: str
    category: str
    chunk: str


SEED_CHUNKS: list[SeedChunk] = [
    SeedChunk(
        "Manali",
        "overview",
        "Manali is ideal for mountain road trips with pine forests, river views, and easy access to Solang Valley and Rohtang Pass. Plan for cool weather and scenic halts.",
    ),
    SeedChunk(
        "Manali",
        "stay",
        "Stay options in Manali often cluster around Old Manali and the Mall Road area, giving travelers quick access to food, views, and parking-friendly lodges.",
    ),
    SeedChunk(
        "Manali",
        "food",
        "Local cafes in Manali serve trout, Himachali thali, wood-fired pizza, and warming soups that suit long driving days in the hills.",
    ),
    SeedChunk(
        "Coorg",
        "overview",
        "Coorg is a lush coffee-country drive with rolling plantations, misty viewpoints, and quiet village roads that reward slow travel.",
    ),
    SeedChunk(
        "Coorg",
        "stay",
        "Homestays and plantation resorts in Coorg are popular for road trippers who want quiet nights, local hospitality, and breakfast included.",
    ),
    SeedChunk(
        "Coorg",
        "food",
        "Coorg cuisine features pandi curry, akki rotti, fresh coffee, and spice-rich dishes that are easy to find near Madikeri and nearby towns.",
    ),
    SeedChunk(
        "Goa",
        "overview",
        "Goa works well for coastal road trips with beach highways, sunset stops, and easy access to forts, Portuguese heritage zones, and nightlife.",
    ),
    SeedChunk(
        "Goa",
        "stay",
        "North Goa offers lively resorts and boutique hotels, while South Goa is better for quieter stays and longer beach walks.",
    ),
    SeedChunk(
        "Goa",
        "food",
        "Seafood shacks, vindaloo, bebinca, and feni tastings are common highlights for food-focused road trip planners in Goa.",
    ),
    SeedChunk(
        "Ooty",
        "overview",
        "Ooty is a classic hill-road destination with tea estates, winding ghat roads, and cool weather that can change quickly after sunset.",
    ),
    SeedChunk(
        "Ooty",
        "stay",
        "Central Ooty stays are convenient for road travelers who want easy parking, short access to viewpoints, and quick access to the town market.",
    ),
    SeedChunk(
        "Ooty",
        "food",
        "Ooty bakeries and tea shops are great for short stops, while South Indian meals and homemade chocolates remain reliable favorites.",
    ),
    SeedChunk(
        "Munnar",
        "overview",
        "Munnar offers tea gardens, mist-filled curves, and scenic waterfall detours that suit a relaxed hill-drive itinerary.",
    ),
    SeedChunk(
        "Munnar",
        "stay",
        "Plantation cottages and mid-range resorts in Munnar are ideal for road trippers looking for sunrise views and a slower pace.",
    ),
    SeedChunk(
        "Munnar",
        "food",
        "Kerala meals, appam, stew, and fresh tea are easy wins in Munnar, especially after long driving stretches.",
    ),
    SeedChunk(
        "Leh",
        "overview",
        "Leh road trips demand careful planning for altitude, fuel, and weather, but reward travelers with stark mountain vistas and dramatic passes.",
    ),
    SeedChunk(
        "Leh",
        "stay",
        "Leh town has compact guesthouses and hotels that are useful for acclimatization, early departures, and gear storage.",
    ),
    SeedChunk(
        "Leh",
        "food",
        "In Leh, Tibetan noodles, momos, butter tea, and simple hearty food are the most practical choices for road travelers.",
    ),
    SeedChunk(
        "Rishikesh",
        "overview",
        "Rishikesh combines riverfront driving, yoga retreats, and quick access to adventure activities along the Ganga corridor.",
    ),
    SeedChunk(
        "Rishikesh",
        "stay",
        "Riverside camps, guesthouses, and wellness stays are all common in Rishikesh and work well for overnight road breaks.",
    ),
    SeedChunk(
        "Rishikesh",
        "food",
        "Vegetarian cafes, local thalis, and light snacks are easy to find in Rishikesh near the main ghats and bridge areas.",
    ),
    SeedChunk(
        "Hampi",
        "overview",
        "Hampi road trips balance temple ruins, rocky terrain, and photogenic sunrise spots that are best explored at an unhurried pace.",
    ),
    SeedChunk(
        "Hampi",
        "stay",
        "Guesthouses near Hampi Bazaar or Hospet can give travelers a practical base with short travel times to the heritage zone.",
    ),
    SeedChunk(
        "Hampi",
        "food",
        "Simple South Indian meals, banana pancakes, and roadside cafes are common around Hampi's travel hubs.",
    ),
    SeedChunk(
        "Andaman",
        "overview",
        "Andaman road planning focuses on ferry timings, island connections, and choosing stays close to beaches and transport hubs.",
    ),
    SeedChunk(
        "Andaman",
        "stay",
        "In Andaman, stay near Port Blair or beach-heavy areas depending on whether the trip prioritizes logistics or leisure.",
    ),
    SeedChunk(
        "Andaman",
        "food",
        "Seafood, coconut-heavy dishes, and simple island snacks are easy to plan around when hopping between ports and beaches.",
    ),
    SeedChunk(
        "Rajasthan",
        "overview",
        "Rajasthan is a strong long-drive circuit with forts, desert highways, and city-to-city road segments that need fuel and rest-stop planning.",
    ),
    SeedChunk(
        "Rajasthan",
        "stay",
        "Heritage havelis, desert camps, and city hotels all work well depending on whether the route includes Jaipur, Jodhpur, Jaisalmer, or Udaipur.",
    ),
    SeedChunk(
        "Rajasthan",
        "food",
        "Dal baati churma, gatte ki sabzi, kachori, and rich sweets are staples for road travelers across Rajasthan.",
    ),
]


def build_documents() -> list[dict[str, str]]:
    """Convert the seed chunks into plain document records."""
    docs: list[dict[str, str]] = []
    for chunk in SEED_CHUNKS:
        docs.append(
            {
                "id": f"{chunk.destination.lower()}-{chunk.category}",
                "destination": chunk.destination,
                "category": chunk.category,
                "content": chunk.chunk,
            }
        )
    return docs


def seed_travel_guides(force: bool = False) -> int:
    """Seed the persistent Chroma collection with local travel guide chunks."""
    collection = get_collection()
    if collection.count() > 0 and not force:
        return collection.count()

    docs = build_documents()
    embeddings = get_embeddings().embed_documents([doc["content"] for doc in docs])
    collection.upsert(
        ids=[doc["id"] for doc in docs],
        documents=[doc["content"] for doc in docs],
        embeddings=embeddings,
        metadatas=[
            {
                "destination": doc["destination"],
                "category": doc["category"],
            }
            for doc in docs
        ],
    )
    return collection.count()


if __name__ == "__main__":
    total = seed_travel_guides(force=True)
    print(f"Seeded {total} travel guide chunks into ChromaDB.")
