"""Relief requests, inventory and distribution inputs."""
from typing import Literal
from pydantic import Field, model_validator
from .auth_schema import Input


class ItemRequest(Input):
    item: str = Field(min_length=2, max_length=100)
    quantity: int = Field(ge=1, le=100000)
    unit: str | None = Field(default=None, min_length=1, max_length=50)
    inventory_id: int | None = Field(default=None, gt=0)


class ReliefCreate(Input):
    items: list[ItemRequest] = Field(default_factory=list, max_length=30)
    location: str = Field(min_length=2, max_length=200)
    incident_id: int | None = Field(default=None, gt=0)
    note: str = Field(default="", max_length=2000)
    kind: Literal["supplies", "rescue_support"] = "supplies"

    @model_validator(mode="after")
    def unique_items(self):
        if self.kind == "supplies" and not self.items:
            raise ValueError("Supply requests require at least one item")
        if self.kind == "rescue_support" and self.items:
            raise ValueError("Rescue support requests use team dispatch, not inventory items")
        names = [(row.item.casefold(), (row.unit or "").casefold()) for row in self.items]
        if len(names) != len(set(names)):
            raise ValueError("Combine repeated items into a single requested quantity")
        return self


class ReliefAssign(Input):
    team_id: int = Field(gt=0)
    note: str = Field(min_length=5, max_length=2000)


class ReliefComplete(Input):
    note: str = Field(min_length=5, max_length=2000)


class IncidentHandoff(Input):
    team_id: int = Field(gt=0)
    note: str = Field(min_length=5, max_length=2000)
    items: list[ItemRequest] = Field(default_factory=list, max_length=30)


class InventoryCreate(Input):
    item: str = Field(min_length=2, max_length=100)
    quantity: int = Field(ge=0, le=10000000)
    unit: str = Field(default="units", min_length=1, max_length=50)
    location: str = Field(min_length=2, max_length=200)


class InventoryUpdate(Input):
    item: str | None = Field(default=None, min_length=2, max_length=100)
    quantity: int | None = Field(default=None, ge=0, le=10000000)
    unit: str | None = Field(default=None, min_length=1, max_length=50)
    location: str | None = Field(default=None, min_length=2, max_length=200)


class DistributionCreate(Input):
    request_id: int = Field(gt=0)
    inventory_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=100000)
    note: str = Field(default="", max_length=2000)
