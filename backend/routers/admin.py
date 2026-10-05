from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.database.models import Alert, Assignment, AuditLog, Campaign, Distribution, Incident, Inventory, Pledge, RefreshToken, ReliefRequest, Shelter, Team, User, News, SafetyTip, RecoveryMail, Donation, utcnow
from backend.schemas import AdminUserCreate, AdminUserUpdate, NewsCreate, NewsUpdate, SafetyTipCreate, SafetyTipUpdate
from backend.utils.security import hash_password
from backend.utils.permissions import require_admin
from backend.services.auth_service import serialize_user, sync_account_membership
from backend.config import settings
from backend.services import apply_changes, audit, get_row, serialize, serialize_incident, validate_team
from backend.services.team_service import available_team_query, operational_team_ids

router = APIRouter(prefix="/api")


def count(db, model, *conditions):
    return db.scalar(select(func.count(model.id)).where(*conditions))


@router.get("/admin/dashboard", tags=["Administration"])
def dashboard(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return {
        "total_users": count(db, User),
        "active_alerts": count(db, Alert, Alert.active.is_(True), (Alert.expires_at.is_(None)) | (Alert.expires_at > utcnow())),
        "total_incidents": count(db, Incident),
        "active_incidents": count(db, Incident, Incident.status.notin_(["resolved", "closed"])),
        "high_severity_reports": count(db, Incident, Incident.severity == "high", Incident.status.notin_(["resolved", "closed"])),
        "teams_available": db.scalar(select(func.count()).select_from(available_team_query().subquery())),
        "teams_assigned": db.scalar(select(func.count()).select_from(operational_team_ids().subquery())),
        "shelter_available_capacity": db.scalar(select(func.coalesce(func.sum(Shelter.capacity - Shelter.occupied), 0)).where(Shelter.status == "open")),
        "relief_inventory_units": db.scalar(select(func.coalesce(func.sum(Inventory.quantity), 0))),
        "pending_relief_requests": count(db, ReliefRequest, ReliefRequest.status != "fulfilled"),
        "donation_pledges": count(db, Pledge),
        "payments_enabled": settings.payment_provider == "razorpay" and bool(settings.razorpay_key_id and settings.razorpay_key_secret),
        "received_donations": count(db, Donation, Donation.sandbox.is_(False)),
        "recent_incidents": [serialize_incident(row, user) for row in db.scalars(select(Incident).order_by(Incident.id.desc()).limit(6))],
    }


def aggregate(db, model, column):
    return dict(db.execute(select(column, func.count(model.id)).group_by(column)).all())


@router.get("/admin/reports", tags=["Administration"])
def reports(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return {
        "incidents_by_status": aggregate(db, Incident, Incident.status),
        "incidents_by_severity": aggregate(db, Incident, Incident.severity),
        "incidents_by_district": aggregate(db, Incident, Incident.district),
        "relief_requests_by_status": aggregate(db, ReliefRequest, ReliefRequest.status),
        "inventory": [serialize(row) for row in db.scalars(select(Inventory))],
        "shelters": [{**serialize(row), "available_capacity": row.capacity - row.occupied if row.status == "open" else 0} for row in db.scalars(select(Shelter))],
        "teams": [serialize(row) for row in db.scalars(select(Team))],
        "distributions": count(db, Distribution),
        "donations": {"pledges": count(db, Pledge), "total_pledged_money": db.scalar(select(func.coalesce(func.sum(Pledge.amount), 0)).where(Pledge.kind == "money")),
            "received_records": count(db, Donation, Donation.sandbox.is_(False)), "received_money": db.scalar(select(func.coalesce(func.sum(Donation.amount), 0)).where(Donation.kind == "money", Donation.sandbox.is_(False))),
            "received_supplies": count(db, Donation, Donation.kind == "supplies", Donation.sandbox.is_(False)), "sandbox_records": count(db, Donation, Donation.sandbox.is_(True)), "payment_status": settings.payment_provider,
            "records": [serialize(row) for row in db.scalars(select(Donation).order_by(Donation.id.desc()))]},
    }


@router.get("/admin/incidents", include_in_schema=False, tags=["Administration"])
def incidents(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [serialize_incident(row, user) for row in db.scalars(select(Incident).order_by(Incident.id.desc()))]


@router.get("/admin/users", tags=["Administration"])
def users(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [serialize_user(row) for row in db.scalars(select(User).order_by(User.id))]


@router.post("/admin/users", status_code=201, tags=["Administration"])
def create_user(body: AdminUserCreate, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if body.role == "response_team" and not body.team_id:
        raise HTTPException(422, "Response team accounts require a team")
    if body.role != "response_team" and body.team_id:
        raise HTTPException(422, "Only response team accounts may have a team")
    validate_team(db, body.team_id)
    row = User(**body.model_dump(exclude={"password"}), password_hash=hash_password(body.password))
    db.add(row)
    try:
        db.flush()
        sync_account_membership(db, row)
        audit(db, user, "user.create", "user", row.id, {"role": row.role})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with this email already exists")
    return serialize_user(row)


@router.put("/admin/users/{user_id}", tags=["Administration"])
def update_user(user_id: int, body: AdminUserUpdate, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = get_row(db, User, user_id, lock=True)
    if user.id == row.id and (body.active is False or body.role not in (None, "admin")):
        raise HTTPException(409, "You cannot deactivate or demote your current administrator account")
    apply_changes(row, body, nullable=("team_id",))
    if row.role == "response_team" and row.team_id is None:
        raise HTTPException(422, "Response team accounts require a team")
    if row.role != "response_team":
        row.team_id = None
    validate_team(db, row.team_id)
    sync_account_membership(db, row)
    # Revoke existing sessions whenever permissions or activation are changed.
    if body.model_fields_set:
        db.execute(update(RefreshToken).where(RefreshToken.user_id == row.id).values(revoked=True))
    audit(db, user, "user.permissions", "user", row.id, {"active": row.active, "role": row.role, "team_id": row.team_id})
    db.commit()
    return serialize_user(row)


@router.get("/admin/audit-logs", tags=["Administration"])
def audit_logs(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [serialize(row) for row in db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(200))]


@router.get("/news", tags=["Community information"])
def news(db: Session = Depends(get_db)):
    return [serialize(row) for row in db.scalars(select(News).where(News.published.is_(True)).order_by(News.id.desc()))]


@router.get("/admin/news", tags=["Community information"])
def news_drafts(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [serialize(row) for row in db.scalars(select(News).order_by(News.id.desc()))]


@router.post("/news", status_code=201, tags=["Community information"])
def create_news(body: NewsCreate, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if body.published:
        raise HTTPException(409, "Create a draft, verify it, then publish it")
    row = News(**body.model_dump())
    db.add(row)
    db.flush()
    audit(db, user, "news.create", "news", row.id)
    db.commit()
    return serialize(row)


@router.put("/news/{news_id}", tags=["Community information"])
def update_news(news_id: int, body: NewsUpdate, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = get_row(db, News, news_id, lock=True)
    if body.model_fields_set & {"title", "content", "source"}:
        row.verified, row.published = False, False
        row.verified_by, row.verified_at, row.verification_note = None, None, ""
    if body.published is True and not row.verified:
        raise HTTPException(409, "Verify this draft before publishing it")
    apply_changes(row, body)
    audit(db, user, "news.update", "news", row.id, {"published": row.published})
    db.commit()
    return serialize(row)


@router.post("/news/{news_id}/verify", tags=["Community information"])
def verify_news(news_id: int, body: dict, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    note = body.get("note", "")
    if not isinstance(note, str) or len(note) > 2000 or set(body) - {"note"}:
        raise HTTPException(422, "Provide an optional verification note up to 2000 characters")
    row = get_row(db, News, news_id, lock=True)
    row.verified, row.verified_by, row.verified_at, row.verification_note = True, user.id, utcnow(), note
    audit(db, user, "news.verify", "news", row.id, {"note": note})
    db.commit()
    return serialize(row)


@router.get("/admin/recovery-mail", tags=["Administration"])
def recovery_mail(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if not settings.demo_mode:
        raise HTTPException(403, "The local recovery mailbox is available only in demo mode")
    return [serialize(row) for row in db.scalars(select(RecoveryMail).where(RecoveryMail.channel == "admin_mailbox").order_by(RecoveryMail.id.desc()).limit(50))]


@router.get("/safety-tips", tags=["Community information"])
def safety_tips(db: Session = Depends(get_db)):
    return [serialize(row) for row in db.scalars(select(SafetyTip).order_by(SafetyTip.id))]


@router.post("/safety-tips", status_code=201, tags=["Community information"])
def create_safety_tip(body: SafetyTipCreate, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = SafetyTip(**body.model_dump())
    db.add(row)
    db.flush()
    audit(db, user, "safety_tip.create", "safety_tip", row.id)
    db.commit()
    return serialize(row)


@router.put("/safety-tips/{tip_id}", tags=["Community information"])
def update_safety_tip(tip_id: int, body: SafetyTipUpdate, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = get_row(db, SafetyTip, tip_id)
    apply_changes(row, body)
    audit(db, user, "safety_tip.update", "safety_tip", row.id)
    db.commit()
    return serialize(row)
