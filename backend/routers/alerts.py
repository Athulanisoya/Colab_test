from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.database.models import User, Alert, utcnow
from backend.schemas import AlertCreate, AlertUpdate
from backend.utils.permissions import require_admin
from backend.utils.jwt import aware
from backend.services.alert_service import active_alert_query
from backend.services import apply_changes, audit, get_row, notify, serialize

router = APIRouter(prefix="/api", tags=["Community information"])


@router.get("/alerts")
def alerts(db: Session = Depends(get_db)):
    return [serialize(row) for row in db.scalars(active_alert_query().order_by(Alert.id.desc()))]


@router.get("/admin/alerts")
def all_alerts(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [serialize(row) for row in db.scalars(select(Alert).order_by(Alert.id.desc()))]


@router.post("/alerts", status_code=201)
def create_alert(body: AlertCreate, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = Alert(**body.model_dump())
    db.add(row)
    db.flush()
    audit(db, user, "alert.create", "alert", row.id)
    if row.active and (row.expires_at is None or aware(row.expires_at) > utcnow()):
        for citizen_id in db.scalars(select(User.id).where(User.district == body.district, User.active.is_(True))):
            notify(db, citizen_id, body.title, body.message)
    db.commit()
    return serialize(row)


@router.put("/alerts/{alert_id}")
def update_alert(alert_id: int, body: AlertUpdate, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = get_row(db, Alert, alert_id)
    apply_changes(row, body, nullable=("expires_at",))
    audit(db, user, "alert.update", "alert", row.id)
    db.commit()
    return serialize(row)


@router.delete("/alerts/{alert_id}")
def expire_alert(alert_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    row = get_row(db, Alert, alert_id)
    row.active = False
    audit(db, user, "alert.expire", "alert", row.id)
    db.commit()
    return {"message": "Alert expired"}
