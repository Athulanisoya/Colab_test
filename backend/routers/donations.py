from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.database.models import User, Campaign, Pledge, Donation, PaymentTransaction, Inventory
from backend.config import settings
from backend.schemas.donation_schema import DonationProof, DonationVerify, PaymentCreate, PaymentSuccess
import hashlib
import hmac
import secrets
from decimal import Decimal
import httpx
from backend.schemas import CampaignCreate, PledgeCreate
from backend.utils.jwt import get_current_user
from backend.utils.permissions import require_admin
from backend.services import apply_changes, audit, get_row, notify, serialize

router = APIRouter(prefix="/api", tags=["Community information"])


def campaign_data(db, row):
    pledged = db.scalar(select(func.coalesce(func.sum(Pledge.amount), 0)).where(Pledge.campaign_id == row.id, Pledge.kind == "money"))
    count = db.scalar(select(func.count(Pledge.id)).where(Pledge.campaign_id == row.id))
    received = db.scalar(select(func.coalesce(func.sum(Donation.amount), 0)).where(Donation.campaign_id == row.id, Donation.kind == "money", Donation.sandbox.is_(False)))
    return {**serialize(row), "pledged_amount": pledged, "pledge_count": count, "received_amount": received,
            "payments_enabled": razorpay_configured(), "offline_available": True}


def razorpay_configured():
    return settings.payment_provider == "razorpay" and bool(settings.razorpay_key_id and settings.razorpay_key_secret)


def pledge_data(db, row):
    receipt = db.scalar(select(Donation).where(Donation.pledge_id == row.id))
    return {**serialize(row), "receipt": serialize(receipt) if receipt else None, "payments_enabled": razorpay_configured()}


def write_lock(db):
    if db.bind.dialect.name == "sqlite":
        db.rollback()
        db.execute(text("BEGIN IMMEDIATE"))


def owned_pledge(db, pledge_id, user, lock=False):
    row = get_row(db, Pledge, pledge_id, lock=lock)
    if row.user_id != user.id:
        raise HTTPException(403, "This donation belongs to another account")
    return row


def record_receipt(db, pledge, method, reference, actor=None, sandbox=False):
    existing = db.scalar(select(Donation).where(Donation.pledge_id == pledge.id))
    if existing:
        return existing
    receipt = Donation(pledge_id=pledge.id, campaign_id=pledge.campaign_id, user_id=pledge.user_id,
        kind=pledge.kind, amount=Decimal(str(pledge.amount)) if pledge.amount is not None else None,
        items=pledge.items, method=method, reference=reference, verified_by=actor.id if actor else None, sandbox=sandbox)
    db.add(receipt)
    pledge.status = "sandbox_completed" if sandbox else "received"
    if pledge.kind == "supplies" and not sandbox:
        for supplied in pledge.items:
            unit = supplied.get("unit") or "units"
            stock = db.scalar(select(Inventory).where(Inventory.item == supplied["item"], Inventory.unit == unit, Inventory.location == "Donation receiving desk").with_for_update())
            if stock:
                stock.quantity += supplied["quantity"]
            else:
                db.add(Inventory(item=supplied["item"], unit=unit, quantity=supplied["quantity"], location="Donation receiving desk"))
    db.flush()
    notify(db, pledge.user_id, "Donation receipt recorded" if not sandbox else "TEST simulation completed",
        "Administrator/provider confirmed receipt. No card charge was performed by the offline workflow." if not sandbox else "TEST ONLY: no funds were transferred; excluded from received donation totals.")
    return receipt


@router.get("/donations/campaigns")
def campaigns(db: Session = Depends(get_db)):
    return [campaign_data(db, row) for row in db.scalars(select(Campaign).where(Campaign.active.is_(True)).order_by(Campaign.id.desc()))]


@router.get("/admin/campaigns")
def all_campaigns(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [campaign_data(db, row) for row in db.scalars(select(Campaign).order_by(Campaign.id.desc()))]


@router.post("/donations/campaigns", status_code=201)
def create_campaign(body: CampaignCreate, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = Campaign(**body.model_dump())
    db.add(row)
    db.flush()
    audit(db, user, "campaign.create", "campaign", row.id)
    db.commit()
    return campaign_data(db, row)


@router.put("/donations/campaigns/{campaign_id}")
def update_campaign(campaign_id: int, body: CampaignCreate, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = get_row(db, Campaign, campaign_id)
    apply_changes(row, body)
    audit(db, user, "campaign.update", "campaign", row.id)
    db.commit()
    return campaign_data(db, row)


@router.post("/donations/pledges", status_code=201)
def pledge(body: PledgeCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    campaign = get_row(db, Campaign, body.campaign_id)
    if not campaign.active:
        raise HTTPException(409, "Campaign is inactive")
    row = Pledge(**body.model_dump(), user_id=user.id)
    db.add(row)
    db.flush()
    audit(db, user, "donation.pledge", "pledge", row.id, {"kind": body.kind})
    notify(db, user.id, "Donation pledge recorded", "This records your intention to donate. No payment was taken.")
    db.commit()
    return {**pledge_data(db, row), "message": "Commitment recorded. Submit receipt details or use configured checkout to complete the donation."}


@router.get("/donations/my")
def my_pledges(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [pledge_data(db, row) for row in db.scalars(select(Pledge).where(Pledge.user_id == user.id).order_by(Pledge.id.desc()))]


@router.get("/donations/pledges")
def all_pledges(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [pledge_data(db, row) for row in db.scalars(select(Pledge).order_by(Pledge.id.desc()))]


@router.post("/donations/{pledge_id}/submit-proof")
def submit_proof(pledge_id: int, body: DonationProof, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    write_lock(db)
    row = owned_pledge(db, pledge_id, user, lock=True)
    if row.status not in ("pledged", "rejected"):
        raise HTTPException(409, "This commitment has already been submitted or completed")
    if (row.kind == "supplies") != (body.method == "supplies"):
        raise HTTPException(422, "Use supplies for item donations and cash/bank transfer for money")
    row.proof_method, row.proof_reference, row.proof_note = body.method, body.reference, body.note
    row.status = "pending_verification"
    audit(db, user, "donation.proof", "pledge", row.id, {"method": body.method})
    for admin_id in db.scalars(select(User.id).where(User.role == "admin", User.active.is_(True))):
        notify(db, admin_id, "Donation receipt needs verification", f"Review commitment #{row.id} before recording receipt.")
    db.commit()
    return pledge_data(db, row)


@router.post("/donations/{pledge_id}/verify")
def verify_donation(pledge_id: int, body: DonationVerify, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    write_lock(db)
    row = get_row(db, Pledge, pledge_id, lock=True)
    if row.status == "received":
        return pledge_data(db, row)
    if row.status != "pending_verification":
        raise HTTPException(409, "Submit actual receipt details before administrator verification")
    if body.approved:
        receipt = record_receipt(db, row, row.proof_method, body.reference or row.proof_reference, user)
        audit(db, user, "donation.receive", "donation", receipt.id, {"method": receipt.method, "note": body.note})
    else:
        row.status = "rejected"
        row.proof_note = body.note or row.proof_note
        audit(db, user, "donation.reject", "pledge", row.id, {"note": body.note})
        notify(db, row.user_id, "Donation proof requires correction", body.note or "Contact the coordinator and submit corrected receipt details.")
    db.commit()
    return pledge_data(db, row)


@router.get("/donations/records")
def donation_records(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [serialize(row) for row in db.scalars(select(Donation).order_by(Donation.id.desc()))]


@router.get("/donations/payment-config")
def payment_config():
    return {"provider": settings.payment_provider, "checkout_configured": razorpay_configured(),
            "key_id": settings.razorpay_key_id if razorpay_configured() else None,
            "offline_available": True, "sandbox_enabled": settings.demo_mode and settings.payment_provider == "sandbox"}


def razorpay_request(method, path, payload=None):
    """Provider credentials stay on the server; errors omit provider response bodies."""
    if not razorpay_configured():
        raise HTTPException(503, "Configure Razorpay credentials or submit an offline donation receipt")
    try:
        with httpx.Client(timeout=20) as client:
            response = client.request(method, "https://api.razorpay.com/v1/" + path,
                auth=(settings.razorpay_key_id, settings.razorpay_key_secret), json=payload)
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "Payment provider unavailable; no receipt was confirmed")


@router.post("/donations/create-payment", status_code=201, responses={
    403: {"description": "The commitment belongs to another account"},
    404: {"description": "The commitment does not exist"},
    409: {"description": "The commitment or existing payment attempt cannot accept a new order"},
    503: {"description": "The payment provider is unconfigured or unavailable; no payment was confirmed"},
})
def create_payment(body: PaymentCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    write_lock(db)
    pledge = owned_pledge(db, body.pledge_id, user, lock=True)
    if pledge.kind != "money" or pledge.status not in ("pledged", "rejected"):
        raise HTTPException(409, "An uncompleted money commitment is required")
    if db.scalar(select(PaymentTransaction.id).where(PaymentTransaction.pledge_id == pledge.id, PaymentTransaction.status == "created")):
        raise HTTPException(409, "An order already exists; complete or cancel that attempt first")
    minor_decimal = Decimal(str(pledge.amount)) * 100
    if minor_decimal != minor_decimal.to_integral_value():
        raise HTTPException(422, "Use an amount with no more than two decimal places")
    amount_minor = int(minor_decimal)
    if settings.payment_provider == "sandbox" and settings.demo_mode:
        order_id, sandbox = "order_TEST_" + secrets.token_hex(12), True
    elif razorpay_configured():
        order = razorpay_request("POST", "orders", {"amount": amount_minor, "currency": "INR", "receipt": f"resq-{pledge.id}-{secrets.token_hex(4)}"})
        if order.get("amount") != amount_minor or order.get("currency") != "INR" or not str(order.get("id", "")).startswith("order_"):
            raise HTTPException(502, "Provider returned an invalid order; no payment confirmed")
        order_id, sandbox = order["id"], not settings.razorpay_key_id.startswith("rzp_live_")
    else:
        raise HTTPException(503, "Online checkout is not configured. Offline administrator-verified donations are available.")
    transaction = PaymentTransaction(pledge_id=pledge.id, provider=settings.payment_provider, provider_order_id=order_id, amount_minor=amount_minor, sandbox=sandbox)
    db.add(transaction)
    db.flush()
    audit(db, user, "payment.order", "payment_transaction", transaction.id, {"sandbox": sandbox})
    db.commit()
    return {"transaction_id": transaction.id, "provider": transaction.provider, "order_id": order_id,
        "amount_minor": amount_minor, "currency": "INR", "key_id": settings.razorpay_key_id if transaction.provider == "razorpay" else None,
        "sandbox": sandbox, "checkout_url": "https://checkout.razorpay.com/v1/checkout.js" if transaction.provider == "razorpay" else None}


@router.post("/donations/payment-success", responses={
    400: {"description": "The payment signature is invalid"},
    403: {"description": "The order belongs to another account"},
    404: {"description": "The order does not exist"},
    409: {"description": "The payment is not an exact captured match for the open order"},
    503: {"description": "The payment provider is unavailable; no receipt was confirmed"},
})
def payment_success(body: PaymentSuccess, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    write_lock(db)
    transaction = db.scalar(select(PaymentTransaction).where(PaymentTransaction.provider_order_id == body.razorpay_order_id).with_for_update())
    if not transaction:
        raise HTTPException(404, "Order not found")
    pledge = owned_pledge(db, transaction.pledge_id, user, lock=True)
    if transaction.provider != "razorpay" or not razorpay_configured():
        raise HTTPException(409, "This order is not a configured Razorpay order")
    expected = hmac.new(settings.razorpay_key_secret.encode(), (transaction.provider_order_id + "|" + body.razorpay_payment_id).encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, body.razorpay_signature):
        raise HTTPException(400, "Invalid payment signature")
    if transaction.status == "captured":
        if transaction.provider_payment_id != body.razorpay_payment_id:
            raise HTTPException(409, "A different payment already completed this order")
        return pledge_data(db, pledge)
    if transaction.status != "created" or pledge.status not in ("pledged", "rejected"):
        raise HTTPException(409, "This payment attempt is no longer open")
    payment = razorpay_request("GET", "payments/" + body.razorpay_payment_id)
    if (payment.get("id") != body.razorpay_payment_id or payment.get("order_id") != transaction.provider_order_id
        or payment.get("amount") != transaction.amount_minor or payment.get("currency") != transaction.currency
        or payment.get("status") != "captured"):
        raise HTTPException(409, "Provider has not confirmed the exact captured order amount and currency")
    transaction.status, transaction.provider_payment_id = "captured", body.razorpay_payment_id
    receipt = record_receipt(db, pledge, "razorpay", body.razorpay_payment_id, sandbox=transaction.sandbox)
    audit(db, user, "payment.capture_verified", "donation", receipt.id, {"sandbox": transaction.sandbox})
    db.commit()
    return pledge_data(db, pledge)


@router.post("/donations/payments/{transaction_id}/simulate")
def simulate_payment(transaction_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not settings.demo_mode or settings.payment_provider != "sandbox":
        raise HTTPException(403, "TEST simulation is enabled only in explicit local sandbox mode")
    write_lock(db)
    transaction = get_row(db, PaymentTransaction, transaction_id, lock=True)
    pledge = owned_pledge(db, transaction.pledge_id, user, lock=True)
    if transaction.provider != "sandbox" or not transaction.sandbox:
        raise HTTPException(403, "Only a TEST order can be simulated")
    if transaction.status == "created" and pledge.status in ("pledged", "rejected"):
        transaction.status, transaction.provider_payment_id = "captured", "pay_TEST_" + secrets.token_hex(12)
        receipt = record_receipt(db, pledge, "sandbox", transaction.provider_payment_id, sandbox=True)
        audit(db, user, "payment.TEST_simulation", "donation", receipt.id, {"sandbox": True})
        db.commit()
    elif transaction.status != "captured":
        raise HTTPException(409, "This TEST attempt is no longer open")
    return pledge_data(db, pledge)


@router.post("/donations/payments/{transaction_id}/cancel")
def cancel_payment(transaction_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    write_lock(db)
    transaction = get_row(db, PaymentTransaction, transaction_id, lock=True)
    owned_pledge(db, transaction.pledge_id, user, lock=True)
    if transaction.status != "created":
        raise HTTPException(409, "A completed payment cannot be cancelled here")
    transaction.status = "cancelled"
    audit(db, user, "payment.attempt_cancel", "payment_transaction", transaction.id)
    db.commit()
    return {"status": "cancelled", "message": "This application attempt was cancelled. This does not refund or cancel a provider-side payment."}
