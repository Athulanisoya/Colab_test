"""Alert and public safety content validation."""
from datetime import datetime
from typing import Literal
from pydantic import Field
from .auth_schema import Input

Severity = Literal["low", "moderate", "high"]


class AlertCreate(Input):
    title: str = Field(min_length=3, max_length=160)
    message: str = Field(min_length=5, max_length=6000)
    location: str = Field(min_length=2, max_length=200)
    district: str = Field(min_length=2, max_length=80)
    severity: Severity = "moderate"
    expires_at: datetime | None = None
    active: bool = True


class AlertUpdate(Input):
    title: str | None = Field(default=None, min_length=3, max_length=160)
    message: str | None = Field(default=None, min_length=5, max_length=6000)
    location: str | None = Field(default=None, min_length=2, max_length=200)
    district: str | None = Field(default=None, min_length=2, max_length=80)
    severity: Severity | None = None
    expires_at: datetime | None = None
    active: bool | None = None


class NewsCreate(Input):
    title: str = Field(min_length=3, max_length=160)
    content: str = Field(min_length=5, max_length=10000)
    source: str = Field(default="ResQ coordination desk", max_length=250)
    published: bool = False


class NewsUpdate(Input):
    title: str | None = Field(default=None, min_length=3, max_length=160)
    content: str | None = Field(default=None, min_length=5, max_length=10000)
    source: str | None = Field(default=None, max_length=250)
    published: bool | None = None


class SafetyTipCreate(Input):
    title: str = Field(min_length=3, max_length=160)
    content: str = Field(min_length=5, max_length=6000)
    category: str = Field(default="flood", max_length=50)
    source: str = Field(default="Project safety guidance", max_length=250)


class SafetyTipUpdate(Input):
    title: str | None = Field(default=None, min_length=3, max_length=160)
    content: str | None = Field(default=None, min_length=5, max_length=6000)
    category: str | None = Field(default=None, max_length=50)
    source: str | None = Field(default=None, max_length=250)
