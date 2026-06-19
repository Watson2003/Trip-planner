from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.graph import trip_planner_graph
from agents.budget_agent import run_budget_agent
from agents.fallbacks import fallback_daily_weather, fallback_route, fallback_route_road
from tools.osm_places import normalize_place_name
from models.database import async_session_maker
from models.schemas import LocationRecommendation, RecommendationCatalog, TripDetailResponse, TripPlanResponse, TripRequest, TripSummaryResponse
from models.trip import Trip, TripReport
from models.user_schemas import UserResponse
from utils.auth import get_current_user
from utils.destination_discovery import discover_destination_places, discovery_catalog_to_recommendation_catalog
from utils.recommendations import build_destination_recommendations

router = APIRouter(tags=["trip"])
logger = logging.getLogger(__name__)


async def get_session() -> AsyncSession:
    async with async_session_maker() as session:
        yield session


def _build_user_input(payload: TripRequest) -> str:
    """Convert structured input into a natural-language prompt for the planner agent."""
    prefs = ", ".join(payload.preferences) if payload.preferences else "no special preferences"
    waypoints = ", ".join(payload.waypoints) if payload.waypoints else "no fixed waypoints"
    travel_dates = payload.dates or (
        f"{payload.travel_dates.start} to {payload.travel_dates.end}" if payload.travel_dates else "unknown"
    )
    vehicle = payload.vehicle
    vehicle_summary = (
        f"Vehicle: {vehicle.vehicle_name} ({vehicle.vehicle_type}, {vehicle.fuel_type}, "
        f"{vehicle.mileage_kmpl} km/l)"
    )
    return (
        f"Plan a road trip from {payload.origin} to {payload.destination}. "
        f"Travel dates: {travel_dates}. "
        f"Budget: INR {payload.budget}. "
        f"Preferences: {prefs}. "
        f"User-provided waypoints: {waypoints}. "
        f"{vehicle_summary}. "
        f"User ID: {payload.user_id}."
    )


def _travel_dates_payload(request: TripRequest) -> dict[str, str]:
    """Always return travel dates as the structured shape the response model expects."""
    if request.travel_dates is not None:
        return request.travel_dates.model_dump()

    if request.dates:
        try:
            start, end = [part.strip() for part in request.dates.split("to", maxsplit=1)]
        except ValueError:
            return {}
        return {"start": start, "end": end}

    return {}


def _request_start_date(request: TripRequest) -> date | None:
    if request.travel_dates is not None:
        try:
            return date.fromisoformat(request.travel_dates.start)
        except ValueError:
            return None

    if request.dates:
        try:
            start, _end = [part.strip() for part in request.dates.split("to", maxsplit=1)]
            return date.fromisoformat(start)
        except ValueError:
            return None

    return None


def _route_locations(origin: str, waypoints: list[str], destination: str) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for location in [origin, *waypoints, destination]:
        normalized = str(location or "").strip()
        if not normalized or normalized.casefold() in seen:
            continue
        seen.add(normalized.casefold())
        ordered.append(normalized)
    return ordered


def _parse_recommendation_blocks(raw: object) -> list[LocationRecommendation]:
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw, list):
        return []
    return [LocationRecommendation.model_validate(item) for item in raw if isinstance(item, dict)]


def _parse_recommendation_catalog(raw: object, destination: str = "") -> RecommendationCatalog:
    if raw is None:
        return RecommendationCatalog(destination=destination)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return RecommendationCatalog(destination=destination)
    if isinstance(raw, list):
        destination_block = next((item for item in raw if isinstance(item, dict) and str(item.get("location", "")).strip().casefold() == destination.casefold()), None)
        block = destination_block if isinstance(destination_block, dict) else next((item for item in raw if isinstance(item, dict)), None)
        if not isinstance(block, dict):
            return RecommendationCatalog(destination=destination)
        raw = block
    if not isinstance(raw, dict):
        return RecommendationCatalog(destination=destination)

    return RecommendationCatalog.model_validate(
        {
            "destination": str(raw.get("destination") or raw.get("location") or destination).strip(),
            "hotels": raw.get("hotels", []),
            "restaurants": raw.get("restaurants", []),
            "attractions": raw.get("attractions", []),
            "fallback_generated": bool(raw.get("fallback_generated", False)),
        }
    )


def _catalog_has_recommendations(catalog: RecommendationCatalog) -> bool:
    return bool(catalog.hotels or catalog.restaurants or catalog.attractions)


def _recommendation_catalog_to_block(catalog: RecommendationCatalog, location: str) -> dict[str, object]:
    return {
        "location": location,
        "hotels": list(catalog.hotels),
        "restaurants": list(catalog.restaurants),
        "attractions": list(catalog.attractions),
        "no_results": {
            "hotels": not bool(catalog.hotels),
            "restaurants": not bool(catalog.restaurants),
            "attractions": not bool(catalog.attractions),
        },
    }


def _fallback_recommendation_catalog(destination: str) -> RecommendationCatalog:
    return RecommendationCatalog(destination=destination, fallback_generated=True)


def _simple_itinerary_from_catalog(
    *,
    origin: str,
    destination: str,
    trip_days: int,
    travel_start: date,
    travel_end: date,
    catalog: RecommendationCatalog,
) -> dict[str, object]:
    def _as_dict_list(items: list[object]) -> list[dict[str, object]]:
        normalized: list[dict[str, object]] = []
        for item in items:
            if hasattr(item, "model_dump"):
                normalized.append(dict(getattr(item, "model_dump")()))
            elif isinstance(item, dict):
                normalized.append(dict(item))
        return normalized

    attractions = _as_dict_list(list(catalog.attractions))
    restaurants = _as_dict_list(list(catalog.restaurants))
    hotels = _as_dict_list(list(catalog.hotels))
    days: list[dict[str, object]] = []
    attraction_index = 0
    restaurant_index = 0

    for day_number in range(1, max(1, trip_days) + 1):
        day_date = travel_start + timedelta(days=day_number - 1)
        if day_number == 1:
            day_title = f"Arrival and Sightseeing - {destination}"
            summary = f"Travel from {origin} to {destination}, then spend the evening exploring the best nearby places."
        elif day_number == trip_days and trip_days >= 3:
            day_title = f"Return Day - {destination} to {origin}"
            summary = f"Enjoy a final morning in {destination} before heading back to {origin}."
        else:
            day_title = f"Destination Exploration - {destination}"
            summary = f"A relaxed day focused on the strongest tourist places in {destination}."

        day_attractions = attractions[attraction_index : attraction_index + (2 if day_number in {1, trip_days} else 3)]
        attraction_index += len(day_attractions)
        breakfast = restaurants[restaurant_index % len(restaurants)] if restaurants else None
        lunch = restaurants[(restaurant_index + 1) % len(restaurants)] if restaurants else None
        dinner = restaurants[(restaurant_index + 2) % len(restaurants)] if restaurants else None
        hotel = hotels[min(day_number - 1, max(0, len(hotels) - 1))] if hotels else None
        restaurant_index += 1

        time_slots: list[dict[str, object]] = []
        if day_number == 1 and breakfast:
            time_slots.append(
                {
                    "time": "08:00 AM",
                    "activity": f"Breakfast at {breakfast['name']}",
                    "place_name": breakfast["name"],
                    "location": origin,
                    "description": breakfast.get("description", ""),
                    "duration_minutes": 40,
                    "category": "breakfast",
                    "estimated_cost_inr": breakfast.get("estimated_cost_inr", 0),
                    "type": "breakfast",
                    "title": f"Breakfast at {breakfast['name']}",
                    "reason": breakfast.get("description", ""),
                    "current_location_before": origin,
                    "current_location_after": origin,
                }
            )
        for index, attraction in enumerate(day_attractions):
            time_slots.append(
                {
                    "time": "10:30 AM" if index == 0 else "02:30 PM",
                    "activity": f"Visit {attraction['name']}",
                    "place_name": attraction["name"],
                    "location": destination,
                    "description": attraction.get("description", ""),
                    "duration_minutes": int(attraction.get("entry_fee_inr", 0) and 90 or 75),
                    "category": "sightseeing",
                    "estimated_cost_inr": attraction.get("entry_fee_inr", 0),
                    "type": "attraction",
                    "title": attraction["name"],
                    "reason": attraction.get("description", ""),
                    "best_time_to_visit": attraction.get("type", ""),
                    "current_location_before": destination,
                    "current_location_after": destination,
                }
            )
            if index == 0 and lunch:
                time_slots.append(
                    {
                        "time": "01:00 PM",
                        "activity": f"Lunch at {lunch['name']}",
                        "place_name": lunch["name"],
                        "location": destination,
                        "description": lunch.get("description", ""),
                        "duration_minutes": 50,
                        "category": "lunch",
                        "estimated_cost_inr": lunch.get("estimated_cost_inr", 0),
                        "type": "lunch",
                        "title": f"Lunch at {lunch['name']}",
                        "reason": lunch.get("description", ""),
                        "current_location_before": destination,
                        "current_location_after": destination,
                    }
                )

        if day_number == 1 and dinner:
            time_slots.append(
                {
                    "time": "07:30 PM",
                    "activity": f"Dinner at {dinner['name']}",
                    "place_name": dinner["name"],
                    "location": destination,
                    "description": dinner.get("description", ""),
                    "duration_minutes": 60,
                    "category": "dinner",
                    "estimated_cost_inr": dinner.get("estimated_cost_inr", 0),
                    "type": "dinner",
                    "title": f"Dinner at {dinner['name']}",
                    "reason": dinner.get("description", ""),
                    "current_location_before": destination,
                    "current_location_after": destination,
                }
            )
        if hotel:
            time_slots.append(
                {
                    "time": "04:30 PM",
                    "activity": f"Check in at {hotel['name']}",
                    "place_name": hotel["name"],
                    "location": destination,
                    "description": hotel.get("description", ""),
                    "duration_minutes": 35,
                    "category": "hotel",
                    "estimated_cost_inr": hotel.get("estimated_cost_inr", 0),
                    "type": "hotel",
                    "title": f"Check in at {hotel['name']}",
                    "reason": hotel.get("description", ""),
                    "current_location_before": destination,
                    "current_location_after": destination,
                }
            )

        days.append(
            {
                "day_number": day_number,
                "date": day_date.isoformat(),
                "day_title": day_title,
                "summary": summary,
                "location": destination if day_number > 1 else f"{origin} to {destination}",
                "time_slots": time_slots,
                "day_total_cost_inr": round(sum(float(slot.get("estimated_cost_inr") or 0) for slot in time_slots), 2),
                "distance_km": 0 if day_number > 1 else 0,
                "driving_hours": 0 if day_number > 1 else 0,
                "highlights": [item["name"] for item in day_attractions[:3]],
            }
        )

    return {
        "trip_id": "fallback-itinerary",
        "origin": origin,
        "destination": destination,
        "total_days": max(1, trip_days),
        "start_date": travel_start.isoformat(),
        "end_date": travel_end.isoformat(),
        "days": days,
        "total_itinerary_cost_inr": round(sum(float(day["day_total_cost_inr"]) for day in days), 2),
        "generated_at": date.today().isoformat(),
        "travel_tips": [
            "Start early to fit the strongest sightseeing stops into daylight.",
            "Keep meals near the attraction clusters to reduce wasted driving time.",
            "Use the first day for arrival, hotel check-in, and light sightseeing.",
        ],
    }


def _validate_recommendation_locations(
    recommendations: list[LocationRecommendation],
    expected_locations: list[str],
) -> list[str]:
    expected_map = {location.casefold(): location for location in expected_locations}
    recommendation_locations: list[str] = []

    for recommendation in recommendations:
        location = str(recommendation.location or "").strip()
        if not location or location.casefold() not in expected_map:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Recommendation location {location!r} does not match the user's trip cities.",
            )
        recommendation_locations.append(expected_map[location.casefold()])

    if not recommendation_locations:
        return expected_locations

    return recommendation_locations


def _normalize_plan_state(state: dict) -> dict:
    """Shape the graph output into a stable response payload."""
    route_data = state.get("route") or {}
    route = {
        "distance_km": route_data.get("distance_km", state.get("route_distance_km")),
        "duration_hours": route_data.get("duration_hours", state.get("route_duration_hours")),
        "polyline": route_data.get("polyline", state.get("polyline", [])),
        "toll_roads": route_data.get("toll_roads", state.get("toll_roads", False)),
    }
    recommendation_catalog = _parse_recommendation_catalog(state.get("recommendation_catalog"), state.get("destination", ""))
    recommendation_blocks = _parse_recommendation_blocks(state.get("recommendations"))
    return {
        "user_id": state.get("user_id", "guest"),
        "origin": state.get("origin", ""),
        "destination": state.get("destination", ""),
        "travel_dates": state.get("travel_dates", {}),
        "budget": state.get("budget", 0.0),
        "preferences": state.get("preferences", []),
        "waypoints": state.get("waypoints", []),
        "route": route,
        "weather": state.get("weather", []),
        "weather_status": state.get("weather_status", "success"),
        "weather_message": state.get("weather_message", ""),
        "recommendations": recommendation_catalog,
        "recommendation_locations": [recommendation_catalog.destination] if recommendation_catalog.destination else [item.location for item in recommendation_blocks],
        "itinerary": state.get("itinerary"),
        "report_summary": state.get("report_summary", ""),
        "pdf_path": state.get("pdf_path"),
        "vehicle": state.get("vehicle"),
        "fuel_calculation": state.get("fuel_calculation"),
        "fuel_cost_inr": state.get("fuel_cost_inr"),
        "toll_cost_inr": state.get("toll_cost_inr"),
        "hotel_cost_inr": state.get("hotel_cost_inr"),
        "hotel_price_per_night": state.get("hotel_price_per_night"),
        "hotel_category": state.get("hotel_category"),
        "hotel_nights": state.get("hotel_nights"),
        "hotel_daily_breakdown": state.get("hotel_daily_breakdown", []),
        "hotel_explanation": state.get("hotel_explanation"),
        "food_cost_inr": state.get("food_cost_inr"),
        "food_price_per_day_per_person": state.get("food_price_per_day_per_person"),
        "food_type": state.get("food_type"),
        "food_days": state.get("food_days"),
        "food_is_vegetarian": state.get("food_is_vegetarian"),
        "food_daily_breakdown": state.get("food_daily_breakdown", []),
        "food_explanation": state.get("food_explanation"),
        "misc_cost_inr": state.get("misc_cost_inr"),
        "number_of_people": state.get("number_of_people"),
        "trip_days": state.get("trip_days"),
        "cost_per_person_inr": state.get("cost_per_person_inr"),
        "total_inr": state.get("total_inr"),
        "total_usd": state.get("total_usd"),
    }


def _align_itinerary_total(itinerary: object, total_inr: object) -> object:
    if itinerary is None or total_inr is None:
        return itinerary

    try:
        resolved_total = round(float(total_inr), 2)
    except (TypeError, ValueError):
        return itinerary

    if isinstance(itinerary, dict):
        return {**itinerary, "total_itinerary_cost_inr": resolved_total}

    if hasattr(itinerary, "model_copy"):
        return itinerary.model_copy(update={"total_itinerary_cost_inr": resolved_total})

    return itinerary


def _trip_summary(trip: Trip) -> TripSummaryResponse:
    return TripSummaryResponse.model_validate(
        {
            "id": trip.id,
            "origin": trip.origin,
            "destination": trip.destination,
            "dates": {
                "start": trip.travel_start_date,
                "end": trip.travel_end_date,
            }
            if trip.travel_start_date and trip.travel_end_date
            else None,
            "budget": trip.budget,
            "created_at": trip.created_at,
        }
    )


@router.post("/trip/plan", response_model=TripPlanResponse, status_code=status.HTTP_201_CREATED)
async def plan_trip(
    request: TripRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserResponse = Depends(get_current_user),
) -> TripPlanResponse:
    print("=== TRIP REQUEST RECEIVED ===")
    print(f"requested_origin = {request.origin}")
    print(f"requested_destination = {request.destination}")
    print(f"normalized_destination = {normalize_place_name(request.destination)}")
    print(f"dates: {request.dates}")
    print(f"trip_days: {request.trip_days}")
    print(f"budget: {request.budget}")
    print(f"preferences: {request.preferences}")

    try:
        discovered_catalog = await discover_destination_places(request.destination, request.preferences)
        discovered_recommendation_catalog = RecommendationCatalog.model_validate(
            discovery_catalog_to_recommendation_catalog(discovered_catalog, request.destination)
        )
        print(f"trip_plan_destination = {request.destination}")
        print(f"discovered_attractions_count = {len(discovered_recommendation_catalog.attractions)}")
        print(f"discovered_restaurants_count = {len(discovered_recommendation_catalog.restaurants)}")
        print(f"discovered_hotels_count = {len(discovered_recommendation_catalog.hotels)}")

        state = {
            "user_input": _build_user_input(request),
            "origin": request.origin,
            "destination": request.destination,
            "travel_dates": _travel_dates_payload(request),
            "dates": request.dates or "",
            "trip_days": int(request.trip_days),
            "budget": request.budget,
            "preferences": request.preferences,
            "waypoints": request.waypoints,
            "user_id": current_user.username,
            "vehicle": request.vehicle.model_dump(),
            "recommendation_catalog": discovered_recommendation_catalog.model_dump(),
            "recommendations": [_recommendation_catalog_to_block(discovered_recommendation_catalog, request.destination)],
            "hotels": list(discovered_recommendation_catalog.hotels),
            "restaurants": list(discovered_recommendation_catalog.restaurants),
            "attractions": list(discovered_recommendation_catalog.attractions),
            "discovered_destination_catalog": discovered_catalog,
        }
        print("=== TRIPSTATE BEING BUILT ===")
        print(f"trip_days going into state: {request.trip_days}")
        print(f"TripState trip_days = {state['trip_days']}")
        print(f"destination_used_for_osm = {request.destination}")
        print(f"destination_used_for_llm = {request.destination}")
        plan_task = asyncio.create_task(trip_planner_graph.ainvoke(state))
        try:
            result_state = await asyncio.wait_for(asyncio.shield(plan_task), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("Trip planning timed out for %s -> %s; returning fallback result.", request.origin, request.destination)
            fallback_state = run_budget_agent(dict(state))
            fallback_route_data = await fallback_route_road(request.origin, request.destination, request.waypoints or [])
            if fallback_route_data is None:
                fallback_route_data = fallback_route(request.origin, request.destination, request.waypoints or [])
            if fallback_route_data is not None:
                fallback_state["route_distance_km"] = fallback_route_data["distance_km"]
                fallback_state["route_duration_hours"] = fallback_route_data["duration_hours"]
                fallback_state["polyline"] = fallback_route_data["polyline"]
                fallback_state["toll_roads"] = fallback_route_data["toll_roads"]
                fallback_state["route"] = {
                    "distance_km": fallback_route_data["distance_km"],
                    "duration_hours": fallback_route_data["duration_hours"],
                    "coordinates": fallback_route_data["polyline"],
                    "origin_coords": fallback_route_data["polyline"][0] if fallback_route_data["polyline"] else None,
                    "destination_coords": fallback_route_data["polyline"][-1] if fallback_route_data["polyline"] else None,
                    "polyline": fallback_route_data["polyline"],
                    "toll_roads": fallback_route_data["toll_roads"],
                }
            fallback_catalog = discovered_recommendation_catalog
            fallback_state["recommendation_catalog"] = fallback_catalog.model_dump()
            fallback_state["recommendations"] = [_recommendation_catalog_to_block(fallback_catalog, fallback_catalog.destination)]
            fallback_state["hotels"] = fallback_catalog.hotels
            fallback_state["restaurants"] = fallback_catalog.restaurants
            fallback_state["attractions"] = fallback_catalog.attractions
            fallback_state["osm_places"] = [*fallback_catalog.hotels, *fallback_catalog.restaurants, *fallback_catalog.attractions]
            start_date = _request_start_date(request) or date.today()
            trip_day_count = max(1, int(request.trip_days or 1))
            fallback_state["weather"] = fallback_daily_weather(request.destination, days=trip_day_count, start_date=start_date)
            fallback_state["weather_status"] = "success"
            fallback_state["weather_message"] = ""
            fallback_state["itinerary"] = _simple_itinerary_from_catalog(
                origin=request.origin,
                destination=request.destination,
                trip_days=trip_day_count,
                travel_start=start_date,
                travel_end=date.fromisoformat(request.travel_dates.end if request.travel_dates else _travel_dates_payload(request).get("end", start_date.isoformat())),
                catalog=fallback_catalog,
            )
            fallback_state["planning_timed_out"] = True
            fallback_state["report_summary"] = fallback_state.get(
                "report_summary",
                f"{request.destination} is a practical road trip destination.",
            )
            result_state = fallback_state
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Trip planning failed: {exc}") from exc

    errors = result_state.get("errors", [])
    if errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=errors)

    trip = Trip(
        user_id=current_user.id,
        origin=result_state.get("origin", request.origin),
        destination=result_state.get("destination", request.destination),
        travel_start_date=request.travel_dates.start if request.travel_dates else request.dates.split(" to ")[0],
        travel_end_date=request.travel_dates.end if request.travel_dates else request.dates.split(" to ")[1],
        budget=request.budget,
        waypoints=result_state.get("waypoints", request.waypoints),
    )
    session.add(trip)
    await session.commit()
    await session.refresh(trip)

    pdf_path = result_state.get("pdf_path")
    recommendation_blocks = _parse_recommendation_blocks(result_state.get("recommendations"))
    recommendation_catalog = _parse_recommendation_catalog(result_state.get("recommendation_catalog"), result_state.get("destination", request.destination))
    if not _catalog_has_recommendations(recommendation_catalog) and not result_state.get("planning_timed_out"):
        discovered_result = result_state.get("discovered_destination_catalog") or discovered_catalog
        if isinstance(discovered_result, dict):
            recommendation_catalog = RecommendationCatalog.model_validate(
                discovery_catalog_to_recommendation_catalog(discovered_result, result_state.get("destination", request.destination))
            )
        else:
            recommendation_catalog = RecommendationCatalog.model_validate(
                await build_destination_recommendations(result_state.get("destination", request.destination))
            )
    if not _catalog_has_recommendations(recommendation_catalog) and isinstance(discovered_catalog, dict):
        recommendation_catalog = RecommendationCatalog.model_validate(
            discovery_catalog_to_recommendation_catalog(discovered_catalog, request.destination)
        )
    expected_locations = _route_locations(
        origin=result_state.get("origin", request.origin),
        waypoints=result_state.get("waypoints", request.waypoints) or [],
        destination=result_state.get("destination", request.destination),
    )
    recommendation_locations = _validate_recommendation_locations(recommendation_blocks, expected_locations)
    trip.recommendations_json = json.dumps(recommendation_catalog.model_dump(), ensure_ascii=False)
    session.add(trip)
    await session.commit()
    await session.refresh(trip)

    report = None
    if pdf_path:
        report = TripReport(trip_id=trip.id, pdf_path=str(pdf_path))
        session.add(report)
        await session.commit()
        await session.refresh(report)

    response_data = _normalize_plan_state(result_state)
    print(f"final_itinerary_destination = {response_data.get('destination', '')}")
    response_data.update(
        {
            "trip_id": trip.id,
            "report_id": report.id if report else None,
            "created_at": trip.created_at,
            "recommendations": recommendation_catalog,
            "recommendation_locations": recommendation_locations,
            "itinerary": _align_itinerary_total(result_state.get("itinerary", None), response_data.get("total_inr")),
        }
    )
    print(f"recommendations_returned_count = {len(recommendation_catalog.hotels) + len(recommendation_catalog.restaurants) + len(recommendation_catalog.attractions)}")
    return TripPlanResponse.model_validate(response_data)


@router.get("/trip/my-trips", response_model=list[TripSummaryResponse])
async def my_trips(
    session: AsyncSession = Depends(get_session),
    current_user: UserResponse = Depends(get_current_user),
) -> list[TripSummaryResponse]:
    result = await session.execute(
        select(Trip).where(Trip.user_id == current_user.id).order_by(Trip.created_at.desc())
    )
    trips = result.scalars().all()
    return [_trip_summary(trip) for trip in trips]


@router.get("/trip/{trip_id}", response_model=TripDetailResponse)
async def get_trip(trip_id: int, session: AsyncSession = Depends(get_session)) -> TripDetailResponse:
    trip_result = await session.execute(select(Trip).where(Trip.id == trip_id))
    trip = trip_result.scalar_one_or_none()
    if trip is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trip not found")

    report_result = await session.execute(
        select(TripReport).where(TripReport.trip_id == trip_id).order_by(TripReport.created_at.desc())
    )
    report = report_result.scalars().first()
    recommendations = _parse_recommendation_catalog(trip.recommendations_json, trip.destination)
    if not _catalog_has_recommendations(recommendations):
        recommendations = RecommendationCatalog.model_validate(await build_destination_recommendations(trip.destination))
    recommendation_locations = [recommendations.destination] if recommendations.destination else [trip.destination]

    return TripDetailResponse(
        id=trip.id,
        user_id=trip.user_id,
        origin=trip.origin,
        destination=trip.destination,
        waypoints=trip.waypoints,
        created_at=trip.created_at,
        pdf_path=report.pdf_path if report else None,
        recommendations=recommendations,
        recommendation_locations=recommendation_locations,
    )


@router.get("/trip/{trip_id}/pdf")
async def get_trip_pdf(trip_id: int, session: AsyncSession = Depends(get_session)) -> FileResponse:
    report_result = await session.execute(
        select(TripReport).where(TripReport.trip_id == trip_id).order_by(TripReport.created_at.desc())
    )
    report = report_result.scalars().first()
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF report not found")

    pdf_path = Path(report.pdf_path)
    if not pdf_path.is_absolute():
        pdf_path = Path(__file__).resolve().parents[1] / pdf_path
    if not pdf_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generated PDF file is missing")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=pdf_path.name,
    )
