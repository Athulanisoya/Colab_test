"""Citizen profile and administrator account inputs."""
from pydantic import Field
from .auth_schema import Input, Register, Role


class UserUpdate(Input):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    district: str | None = Field(default=None, min_length=2, max_length=80)


class AdminUserUpdate(Input):
    active: bool | None = None
    role: Role | None = None
    team_id: int | None = Field(default=None, gt=0)


class AdminUserCreate(Register):
    role: Role = "response_team"
    team_id: int | None = Field(default=None, gt=0)
