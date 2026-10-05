"""Donation campaign and money or supplies pledge inputs."""
from typing import Literal
from pydantic import Field, model_validator
from .auth_schema import Input
from .relief_schema import ItemRequest
from decimal import Decimal


class CampaignCreate(Input):
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=5, max_length=6000)
    target_amount: float = Field(default=0, ge=0, le=100000000, allow_inf_nan=False)
    active: bool = True


class PledgeCreate(Input):
    campaign_id: int = Field(gt=0)
    kind: Literal["money", "supplies"]
    amount: float | None = Field(default=None, gt=0, le=10000000, allow_inf_nan=False)
    items: list[ItemRequest] | None = Field(default=None, max_length=30)
    note: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def valid_pledge(self):
        if self.kind == "money" and (self.amount is None or self.items):
            raise ValueError("Money pledges require an amount and no supplies")
        if self.kind == "money" and Decimal(str(self.amount)) != Decimal(str(self.amount)).quantize(Decimal("0.01")):
            raise ValueError("Money amounts must have at most two decimal places")
        if self.kind == "supplies" and (not self.items or self.amount is not None):
            raise ValueError("Supply pledges require items and no money amount")
        return self


class DonationProof(Input):
    method: Literal["cash", "bank_transfer", "supplies"]
    reference: str = Field(min_length=3, max_length=200)
    note: str = Field(default="", max_length=2000)


class DonationVerify(Input):
    approved: bool
    reference: str = Field(default="", max_length=200)
    note: str = Field(default="", max_length=2000)


class PaymentCreate(Input):
    pledge_id: int = Field(gt=0)


class PaymentSuccess(Input):
    razorpay_order_id: str = Field(min_length=5, max_length=100, pattern="^order_[A-Za-z0-9_]+$")
    razorpay_payment_id: str = Field(min_length=5, max_length=100, pattern="^pay_[A-Za-z0-9_]+$")
    razorpay_signature: str = Field(min_length=64, max_length=64, pattern="^[a-f0-9]{64}$")
