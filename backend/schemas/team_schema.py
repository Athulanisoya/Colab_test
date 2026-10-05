"""Response team management and assignment inputs."""
from typing import Literal
from pydantic import Field
from .auth_schema import Input

TeamType = Literal["rescue", "investigation", "relief", "shelter"]


class AssignTeam(Input):
    incident_id: int = Field(gt=0)
    team_id: int = Field(gt=0)
    note: str = Field(default="", max_length=2000)


class TaskAcceptance(Input):
    note: str = Field(default="", max_length=2000)


class TeamCreate(Input):
    name: str = Field(min_length=2, max_length=120)
    team_type: TeamType
    district: str = Field(min_length=2, max_length=80)
    available: bool = True


class TeamUpdate(Input):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    team_type: TeamType | None = None
    district: str | None = Field(default=None, min_length=2, max_length=80)
    available: bool | None = None
