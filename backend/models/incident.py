"""SQLAlchemy incident domain tables."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.connection import Base
from .user import utcnow



class Incident(Base):
    __tablename__ = "incident_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(30), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    message: Mapped[str] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(200))
    district: Mapped[str] = mapped_column(String(80))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    geocoding_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    people_affected: Mapped[int | None] = mapped_column(Integer)
    help_required: Mapped[list] = mapped_column(JSON, default=list)
    disaster_type: Mapped[str] = mapped_column(String(50), default="flood")
    disaster_type_id: Mapped[int | None] = mapped_column(ForeignKey("disaster_types.id"))
    status: Mapped[str] = mapped_column(String(30), default="submitted", index=True)
    severity: Mapped[str] = mapped_column(String(20), default="pending")
    verified: Mapped[bool | None] = mapped_column(Boolean)
    photo_url: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    analysis: Mapped["ReportAnalysis | None"] = relationship(uselist=False, cascade="all, delete-orphan")
    history: Mapped[list["StatusHistory"]] = relationship(order_by="StatusHistory.id", cascade="all, delete-orphan")
    assignments: Mapped[list["Assignment"]] = relationship(order_by="Assignment.id", cascade="all, delete-orphan")


class ReportAnalysis(Base):
    __tablename__ = "report_analysis"
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incident_reports.id"), unique=True)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    history: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StatusHistory(Base):
    __tablename__ = "status_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incident_reports.id"), index=True)
    status: Mapped[str] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(Text, default="")
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Assignment(Base):
    __tablename__ = "assignments"
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incident_reports.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    assigned_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    team: Mapped["Team"] = relationship()


class InvestigationReport(Base):
    __tablename__ = "investigation_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incident_reports.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    verified: Mapped[bool] = mapped_column(Boolean)
    people_affected: Mapped[int] = mapped_column(Integer)
    required_items: Mapped[list] = mapped_column(JSON, default=list)
    findings: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DisasterType(Base):
    __tablename__ = "disaster_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)


class SeverityPrediction(Base):
    __tablename__ = "severity_predictions"
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incident_reports.id"), index=True)
    severity: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float | None] = mapped_column(Float)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AlertMatch(Base):
    __tablename__ = "alert_matches"
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incident_reports.id"), index=True)
    alert_id: Mapped[int | None] = mapped_column(ForeignKey("alerts.id"))
    status: Mapped[str] = mapped_column(String(20))
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
