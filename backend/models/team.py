"""SQLAlchemy team domain tables."""

from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.connection import Base
from .user import utcnow



class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    team_type: Mapped[str] = mapped_column(String(30))
    district: Mapped[str] = mapped_column(String(80))
    available: Mapped[bool] = mapped_column(Boolean, default=True)


class TeamMember(Base):
    __tablename__ = "team_members"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), primary_key=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
