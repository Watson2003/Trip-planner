from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.graph import trip_planner_graph
from models.database import async_session_maker
from models.schemas import TripDetailResponse, TripPlanResponse, TripRequest
from models.trip import Trip, TripReport

router = APIRouter(tags=["trip"])


async def get_session() -> AsyncSession:
    async with async_session_maker() as session:
        yield session


def _build_user_input(payload: TripRequest) -> str:
    """Convert structured input into a natural-language prompt for the planner agent."""
    prefs = ", ".join(payload.preferences) if payload.preferences else "no special preferences"
    waypoints = ", ".join(payload.waypoints) if payload.waypoints else "no fixed waypoints"
    return (
        f"Plan a road trip from {payload.origin} to {payload.destination}. "
        f"Travel dates: {payload.travel_dates.start} to {payload.travel_dates.end}. "
        f"Budget: INR {payload.budget}. "
        f"Preferences: {prefs}. "
        f"User-provided waypoints: {waypoints}. "
        f"User ID: {payload.user_id}."
    )


def _normalize_plan_state(state: dict) -> dict:
    """Shape the graph output into a stable response payload."""
    route = {
        "distance_km": state.get("route_distance_km"),
        "duration_hours": state.get("route_duration_hours"),
        "polyline": state.get("polyline", []),
        "toll_roads": state.get("toll_roads", False),
    }
    recommendations = {
        "hotels": state.get("hotels", []),
        "restaurants": state.get("restaurants", []),
        "attractions": state.get("attractions", []),
    }
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
        "recommendations": recommendations,
        "report_summary": state.get("report_summary", ""),
        "pdf_path": state.get("pdf_path"),
        "fuel_cost_inr": state.get("fuel_cost_inr"),
        "toll_cost_inr": state.get("toll_cost_inr"),
        "hotel_cost_inr": state.get("hotel_cost_inr"),
        "food_cost_inr": state.get("food_cost_inr"),
        "total_inr": state.get("total_inr"),
        "total_usd": state.get("total_usd"),
    }


@router.post("/trip/plan", response_model=TripPlanResponse, status_code=status.HTTP_201_CREATED)
async def plan_trip(payload: TripRequest, session: AsyncSession = Depends(get_session)) -> TripPlanResponse:
    try:
        initial_state = {
            "user_input": _build_user_input(payload),
            "origin": payload.origin,
            "destination": payload.destination,
            "travel_dates": payload.travel_dates.model_dump(),
            "budget": payload.budget,
            "preferences": payload.preferences,
            "waypoints": payload.waypoints,
            "user_id": payload.user_id,
        }
        result_state = await trip_planner_graph.ainvoke(initial_state)
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
        user_id=payload.user_id,
        origin=result_state.get("origin", payload.origin),
        destination=result_state.get("destination", payload.destination),
        waypoints=result_state.get("waypoints", payload.waypoints),
    )
    session.add(trip)
    await session.commit()
    await session.refresh(trip)

    pdf_path = result_state.get("pdf_path")
    report = None
    if pdf_path:
        report = TripReport(trip_id=trip.id, pdf_path=str(pdf_path))
        session.add(report)
        await session.commit()
        await session.refresh(report)

    response_data = _normalize_plan_state(result_state)
    response_data.update(
        {
            "trip_id": trip.id,
            "report_id": report.id if report else None,
            "created_at": trip.created_at,
        }
    )
    return TripPlanResponse.model_validate(response_data)


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

    return TripDetailResponse(
        id=trip.id,
        user_id=trip.user_id,
        origin=trip.origin,
        destination=trip.destination,
        waypoints=trip.waypoints,
        created_at=trip.created_at,
        pdf_path=report.pdf_path if report else None,
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
