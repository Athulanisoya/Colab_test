"""SQLAlchemy inventory domain tables."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.connection import Base
from .user import utcnow



class Inventory(Base):
    __tablename__ = "inventory"
    id: Mapped[int] = mapped_column(primary_key=True)
    item: Mapped[str] = mapped_column(String(100))
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    unit: Mapped[str] = mapped_column(String(50), default="units")
    location: Mapped[str] = mapped_column(String(200))


class ReliefRequest(Base):
    __tablename__ = "relief_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    incident_id: Mapped[int | None] = mapped_column(ForeignKey("incident_reports.id"))
    assigned_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    kind: Mapped[str] = mapped_column(String(30), default="supplies")
    items: Mapped[list] = mapped_column(JSON)
    location: Mapped[str] = mapped_column(String(200))
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Distribution(Base):
    __tablename__ = "distributions"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("relief_requests.id"), index=True)
    inventory_id: Mapped[int] = mapped_column(ForeignKey("inventory.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    item: Mapped[str] = mapped_column(String(100), default="")
    unit: Mapped[str] = mapped_column(String(50), default="units")
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
