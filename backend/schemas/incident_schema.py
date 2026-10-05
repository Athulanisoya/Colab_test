"""Citizen incident, review, investigation and assistance inputs."""
from typing import Literal
from pydantic import Field, field_validator, model_validator
from .auth_schema import Input

Status = Literal["submitted", "under_review", "team_assigned", "task_accepted", "en_route", "in_progress", "resolved", "closed"]


class IncidentCreate(Input):
    message: str = Field(min_length=5, max_length=6000)
    location: str = Field(default="", max_length=200)
    district: str = Field(default="", max_length=80)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    people_affected: int | None = Field(default=None, ge=0, le=100000)
    help_required: list[str] = Field(default_factory=list, max_length=20)
    disaster_type: Literal["flood"] = "flood"
    geocoding_consent: bool = False

    @field_validator("help_required")
    @classmethod
    def validate_help(cls, value):
        if any(not item.strip() or len(item) > 100 for item in value):
            raise ValueError("Assistance names must contain 1 to 100 characters")
        return list(dict.fromkeys(item.strip() for item in value))

    @model_validator(mode="after")
    def paired_coordinates(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Provide both latitude and longitude")
        return self


class Review(Input):
    verified: bool
    note: str = Field(default="", max_length=2000)


class StatusUpdate(Input):
    status: Status
    note: str = Field(default="", max_length=2000)


class InvestigationCreate(Input):
    verified: bool
    people_affected: int = Field(ge=0, le=100000)
    required_items: list[str] = Field(default_factory=list, max_length=30)
    findings: str = Field(min_length=5, max_length=6000)


class ChatInput(Input):
    message: str = Field(min_length=2, max_length=2000)
    session_id: int | None = Field(default=None, gt=0)


class ClarificationReply(Input):
    answer: str = Field(min_length=2, max_length=2000)
    location: str | None = Field(default=None, min_length=2, max_length=200)
    district: str | None = Field(default=None, min_length=2, max_length=80)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    people_affected: int | None = Field(default=None, ge=0, le=100000)
    landmark: str | None = Field(default=None, min_length=2, max_length=200)

    @model_validator(mode="after")
    def paired_coordinates(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Provide both latitude and longitude")
        return self


class MonitoringDecision(Input):
    note: str = Field(min_length=5, max_length=2000)
    action: Literal["monitor", "investigate"] = "monitor"


class AIInput(Input):
    message: str = Field(min_length=2, max_length=4000)
    location: str = Field(default="", max_length=200)
    district: str = Field(default="", max_length=80)
    people_affected: int | None = Field(default=None, ge=0, le=100000)
    help_required: list[str] = Field(default_factory=list, max_length=20)
    geocoding_consent: bool = False
