from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from agents.itinerary_agent import run_itinerary_agent
from utils.auth import get_current_user

router = APIRouter(prefix="/api/itinerary", tags=["itinerary"])


def _normalize_recommendations(raw: object) -> list[dict]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        destination = str(raw.get("destination") or raw.get("location") or "").strip()
        return [
            {
                "location": destination,
                "hotels": raw.get("hotels", []) if isinstance(raw.get("hotels", []), list) else [],
                "restaurants": raw.get("restaurants", []) if isinstance(raw.get("restaurants", []), list) else [],
                "attractions": raw.get("attractions", []) if isinstance(raw.get("attractions", []), list) else [],
                "fallback_generated": bool(raw.get("fallback_generated", False)),
            }
        ]
    return []


@router.post("/generate")
async def generate_itinerary(request: dict, current_user=Depends(get_current_user)):
    """
    Generate itinerary for an existing trip.
    Accepts same fields as trip plan request.
    Returns full day-by-day itinerary.
    """
    try:
        state = {
            "origin": request.get("origin"),
            "destination": request.get("destination"),
            "dates": request.get("dates"),
            "trip_days": request.get("trip_days", 1),
            "budget": request.get("budget", 15000),
            "preferences": request.get("preferences", []),
            "vehicle": request.get("vehicle", {}),
            "route": request.get("route", {}),
            "weather": request.get("weather", []),
            "recommendations": _normalize_recommendations(request.get("recommendations", [])),
        }

        result = run_itinerary_agent(state)

        if result.get("itinerary"):
            return {
                "status": "success",
                "itinerary": result["itinerary"],
            }

        raise HTTPException(status_code=500, detail="Failed to generate itinerary")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trip/{trip_id}")
async def get_trip_itinerary(trip_id: str, current_user=Depends(get_current_user)):
    """
    Get saved itinerary for a trip by trip_id.
    """
    return {
        "status": "success",
        "trip_id": trip_id,
        "message": "Use /generate endpoint with trip data",
    }
