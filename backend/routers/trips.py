from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import async_session_maker
from models.schemas import TripCreate, TripRead
from models.trip import Trip
from utils.auth import get_or_create_user_from_identifier

router = APIRouter(tags=["trips"])


async def get_session() -> AsyncSession:
    async with async_session_maker() as session:
        yield session


@router.post("/trips", response_model=TripRead, status_code=status.HTTP_201_CREATED)
async def create_trip(payload: TripCreate, session: AsyncSession = Depends(get_session)) -> TripRead:
    user = await get_or_create_user_from_identifier(session, payload.user_id)
    trip = Trip(user_id=user.id, origin=payload.origin, destination=payload.destination, waypoints=payload.waypoints)
    session.add(trip)
    await session.commit()
    await session.refresh(trip)
    return TripRead.model_validate(
        {
            "id": trip.id,
            "user_id": trip.user_id,
            "origin": trip.origin,
            "destination": trip.destination,
            "waypoints": trip.waypoints,
            "created_at": trip.created_at,
        }
    )


@router.get("/trips", response_model=list[TripRead])
async def list_trips(session: AsyncSession = Depends(get_session)) -> list[TripRead]:
    result = await session.execute(select(Trip).order_by(Trip.created_at.desc()))
    trips = result.scalars().all()
    return [
        TripRead.model_validate(
            {
                "id": trip.id,
                "user_id": trip.user_id,
                "origin": trip.origin,
                "destination": trip.destination,
                "waypoints": trip.waypoints,
                "created_at": trip.created_at,
            }
        )
        for trip in trips
    ]


@router.get("/trips/{trip_id}", response_model=TripRead)
async def get_trip(trip_id: int, session: AsyncSession = Depends(get_session)) -> TripRead:
    result = await session.execute(select(Trip).where(Trip.id == trip_id))
    trip = result.scalar_one_or_none()
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return TripRead.model_validate(
        {
            "id": trip.id,
            "user_id": trip.user_id,
            "origin": trip.origin,
            "destination": trip.destination,
            "waypoints": trip.waypoints,
            "created_at": trip.created_at,
        }
    )
