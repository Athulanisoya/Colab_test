from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.database.models import User, Notification
from backend.schemas import UserUpdate
from backend.utils.jwt import get_current_user
from backend.services.auth_service import serialize_user
from backend.services import apply_changes, audit, get_row, serialize

router = APIRouter(prefix="/api")


@router.get("/users/me", tags=["Authentication"])
def me(user: User = Depends(get_current_user)):
    return serialize_user(user)


@router.put("/users/me", tags=["Authentication"])
def update_me(body: UserUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    apply_changes(user, body)
    audit(db, user, "user.profile", "user", user.id)
    db.commit()
    return serialize_user(user)


@router.get("/notifications", tags=["Community information"])
def notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [serialize(row) for row in db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.id.desc()).limit(100))]


@router.post("/notifications/{notification_id}/read", tags=["Community information"])
def read_notification(notification_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = get_row(db, Notification, notification_id)
    if row.user_id != user.id:
        raise HTTPException(403, "This notification belongs to another user")
    row.read = True
    db.commit()
    return serialize(row)
