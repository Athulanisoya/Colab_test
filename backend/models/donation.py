"""SQLAlchemy donation domain tables."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, JSON, Numeric, String, Text
from decimal import Decimal
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.connection import Base
from .user import utcnow



class Campaign(Base):
    __tablename__ = "donation_campaigns"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    target_amount: Mapped[float] = mapped_column(Float, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Pledge(Base):
    __tablename__ = "donation_pledges"
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("donation_campaigns.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(20))
    amount: Mapped[float | None] = mapped_column(Float)
    items: Mapped[list | None] = mapped_column(JSON)
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="pledged")
    proof_method: Mapped[str | None] = mapped_column(String(30))
    proof_reference: Mapped[str | None] = mapped_column(String(200))
    proof_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Donation(Base):
    __tablename__ = "donations"
    id: Mapped[int] = mapped_column(primary_key=True)
    pledge_id: Mapped[int] = mapped_column(ForeignKey("donation_pledges.id"), unique=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("donation_campaigns.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    items: Mapped[list | None] = mapped_column(JSON)
    method: Mapped[str] = mapped_column(String(30))
    reference: Mapped[str] = mapped_column(String(200))
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    sandbox: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    pledge_id: Mapped[int] = mapped_column(ForeignKey("donation_pledges.id"), index=True)
    provider: Mapped[str] = mapped_column(String(30))
    provider_order_id: Mapped[str] = mapped_column(String(100), unique=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    amount_minor: Mapped[int] = mapped_column()
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(String(30), default="created")
    sandbox: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
