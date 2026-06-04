from __future__ import annotations

from pathlib import Path
from typing import Any

from agents.state import TripState
from rag.retriever import retrieve_travel_info
from tools import generate_pdf_report


async def _build_recommendations(rag_context: list[dict[str, Any]], category: str, destination: str) -> list[dict[str, Any]]:
    return [
        {
            "name": item["destination"] or f"{destination} {category.title()} Option {index + 1}",
            "description": item["content"],
            "category": category,
            "why_it_fits": item["content"],
        }
        for index, item in enumerate(rag_context[:3])
    ]


def _fallback_recommendations(category: str, destination: str) -> list[dict[str, Any]]:
    """Produce lightweight recommendations when RAG is unavailable."""
    readable_category = category.title()
    base_name = destination or "Your destination"
    return [
        {
            "name": f"{base_name} {readable_category} {index + 1}",
            "description": (
                f"Suggested {category} stop for {base_name}. "
                "Use it as a practical fallback when curated travel guides are unavailable."
            ),
            "category": category,
            "why_it_fits": f"Fallback {category} option for {base_name}.",
        }
        for index in range(3)
    ]


def _make_pdf(state: TripState, hotels: list[dict[str, Any]], restaurants: list[dict[str, Any]], attractions: list[dict[str, Any]]) -> str:
    # Keep generated reports inside the backend tree so download endpoints can resolve them consistently.
    report_dir = Path(__file__).resolve().parents[1] / "reports"
    report_dir.mkdir(exist_ok=True)
    pdf_path = report_dir / f"trip_report_{state.get('user_id', 'guest')}.pdf"

    generate_pdf_report(
        {
            "origin": state.get("origin", ""),
            "destination": state.get("destination", ""),
            "travel_dates": state.get("travel_dates", {}),
            "route": {
                "distance_km": state.get("route_distance_km", 0),
                "duration_hours": state.get("route_duration_hours", 0),
                "toll_roads": state.get("toll_roads", False),
            },
            "weather": state.get("weather", []),
            "budget": {
                "fuel": state.get("fuel_cost_inr", 0),
                "tolls": state.get("toll_cost_inr", 0),
                "hotels": state.get("hotel_cost_inr", 0),
                "food": state.get("food_cost_inr", 0),
                "miscellaneous": state.get("miscellaneous_cost_inr", 0),
                "total_inr": state.get("total_inr", 0),
                "total_usd": state.get("total_usd", 0),
            },
            "waypoints": state.get("waypoints", []),
            "report_summary": state.get("report_summary", ""),
            "recommendations": {
                "hotels": hotels,
                "restaurants": restaurants,
                "attractions": attractions,
            },
        },
        str(pdf_path),
    )
    return str(pdf_path)


async def recommendation_agent(state: TripState) -> TripState:
    destination = state.get("destination", "")
    preference_blob = ", ".join(state.get("preferences", []))

    # Pull the most relevant travel guide context before synthesizing suggestions.
    rag_context: list[dict[str, Any]] = []
    try:
        rag_context = retrieve_travel_info(
            query=f"{destination} road trip {preference_blob} hotels restaurants attractions local guide",
            k=6,
        )
    except Exception as exc:
        state.setdefault("errors", [])
        state.setdefault("warnings", []).append(f"Travel guide lookup failed: {exc}")
    state["rag_context"] = rag_context

    try:
        hotel_context = retrieve_travel_info(f"{destination} hotel stay parking breakfast", k=4)
    except Exception:
        hotel_context = []
    try:
        restaurant_context = retrieve_travel_info(f"{destination} restaurant food local cuisine", k=4)
    except Exception:
        restaurant_context = []
    try:
        attraction_context = retrieve_travel_info(f"{destination} attraction sightseeing scenic spots", k=4)
    except Exception:
        attraction_context = []

    hotels = await _build_recommendations(hotel_context, "hotel", destination) if hotel_context else _fallback_recommendations("hotel", destination)
    restaurants = await _build_recommendations(restaurant_context, "restaurant", destination) if restaurant_context else _fallback_recommendations("restaurant", destination)
    attractions = await _build_recommendations(attraction_context, "attraction", destination) if attraction_context else _fallback_recommendations("attraction", destination)

    pdf_path = None
    try:
        pdf_path = _make_pdf(state, hotels, restaurants, attractions)
    except Exception as exc:
        state.setdefault("warnings", []).append(f"PDF report generation failed: {exc}")

    summary_payload = {
        "summary": (
            f"{destination} is a strong road trip match for {state.get('origin', 'your origin')} "
            f"with practical stops for hotels, food, and attractions."
        ),
        "highlights": [
            f"Route length: {state.get('route_distance_km', 0)} km",
            f"Estimated budget: INR {state.get('total_inr', 0)}",
            f"Top preference set: {preference_blob or 'general comfort'}",
        ],
    }

    state["hotels"] = hotels
    state["restaurants"] = restaurants
    state["attractions"] = attractions
    state["pdf_path"] = pdf_path
    state["report_summary"] = summary_payload.get("summary", "Trip summary generated.")
    state["trip_report"] = {
        "summary": state["report_summary"],
        "highlights": summary_payload.get("highlights", []),
        "pdf_path": pdf_path,
        "rag_context": rag_context,
    }
    return state
