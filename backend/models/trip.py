from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    origin: Mapped[str] = mapped_column(String(255), nullable=False)
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    waypoints: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    reports: Mapped[list["TripReport"]] = relationship(
        back_populates="trip",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class TripReport(Base):
    __tablename__ = "trip_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, index=True)
    pdf_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    trip: Mapped[Trip] = relationship(back_populates="reports")

