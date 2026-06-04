from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import async_session_maker
from models.schemas import TripCreate, TripRead
from models.trip import Trip

router = APIRouter(tags=["trips"])


async def get_session() -> AsyncSession:
    async with async_session_maker() as session:
        yield session


@router.post("/trips", response_model=TripRead, status_code=status.HTTP_201_CREATED)
async def create_trip(payload: TripCreate, session: AsyncSession = Depends(get_session)) -> Trip:
    trip = Trip(**payload.model_dump())
    session.add(trip)
    await session.commit()
    await session.refresh(trip)
    return trip


@router.get("/trips", response_model=list[TripRead])
async def list_trips(session: AsyncSession = Depends(get_session)) -> list[Trip]:
    result = await session.execute(select(Trip).order_by(Trip.created_at.desc()))
    return list(result.scalars().all())


@router.get("/trips/{trip_id}", response_model=TripRead)
async def get_trip(trip_id: int, session: AsyncSession = Depends(get_session)) -> Trip:
    result = await session.execute(select(Trip).where(Trip.id == trip_id))
    trip = result.scalar_one_or_none()
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip

