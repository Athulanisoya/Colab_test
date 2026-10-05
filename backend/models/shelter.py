"""SQLAlchemy shelter domain tables."""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.connection import Base
from .user import utcnow



class Shelter(Base):
    __tablename__ = "shelters"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    location: Mapped[str] = mapped_column(String(200))
    district: Mapped[str] = mapped_column(String(80))
    capacity: Mapped[int] = mapped_column(Integer)
    occupied: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="open")
    facilities: Mapped[list] = mapped_column(JSON, default=list)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ShelterUpdateRecord(Base):
    __tablename__ = "shelter_updates"
    id: Mapped[int] = mapped_column(primary_key=True)
    shelter_id: Mapped[int] = mapped_column(ForeignKey("shelters.id"), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ShelterOccupancy(Base):
    __tablename__ = "shelter_occupancy"
    id: Mapped[int] = mapped_column(primary_key=True)
    shelter_id: Mapped[int] = mapped_column(ForeignKey("shelters.id"), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    occupied: Mapped[int] = mapped_column(Integer)
    capacity: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
