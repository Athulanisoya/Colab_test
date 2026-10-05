"""Shelter capacity, occupancy and location inputs."""
from pydantic import Field, model_validator
from typing import Literal
from .auth_schema import Input


class ShelterCreate(Input):
    name: str = Field(min_length=2, max_length=160)
    location: str = Field(min_length=2, max_length=200)
    district: str = Field(min_length=2, max_length=80)
    capacity: int = Field(ge=1, le=100000)
    occupied: int = Field(default=0, ge=0, le=100000)
    facilities: list[str] = Field(default_factory=list, max_length=30)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    team_id: int | None = Field(default=None, gt=0)
    status: Literal["open", "full", "closed"] = "open"

    @model_validator(mode="after")
    def check_capacity(self):
        if self.occupied > self.capacity:
            raise ValueError("Occupied beds cannot exceed capacity")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Provide both latitude and longitude")
        return self


class ShelterUpdate(Input):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    location: str | None = Field(default=None, min_length=2, max_length=200)
    district: str | None = Field(default=None, min_length=2, max_length=80)
    capacity: int | None = Field(default=None, ge=1, le=100000)
    occupied: int | None = Field(default=None, ge=0, le=100000)
    facilities: list[str] | None = Field(default=None, max_length=30)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    team_id: int | None = Field(default=None, gt=0)
    status: Literal["open", "full", "closed"] | None = None
