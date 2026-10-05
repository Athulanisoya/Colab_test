import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database.connection import get_db
from backend.database.models import PasswordReset, RefreshToken, User, utcnow
from backend.schemas import ForgotPassword, Login, Register, ResetPassword, TokenBody
from backend.utils.jwt import aware, bearer, decode_access_token, get_current_user
from backend.utils.security import hash_password, token_hash, verify_password
from backend.services.auth_service import issue_tokens, deliver_reset, recovery_delivery_configured
from backend.services import audit

router = APIRouter(prefix="/api", tags=["Authentication"])


@router.post("/auth/register", status_code=201)
def register(body: Register, db: Session = Depends(get_db)):
    if db.scalar(select(User.id).where(User.email == body.email)):
        raise HTTPException(409, "An account with this email already exists")
    user = User(name=body.name, email=body.email, password_hash=hash_password(body.password), district=body.district)
    db.add(user)
    try:
        db.flush()
        tokens = issue_tokens(db, user)
        audit(db, user, "auth.register", "user", user.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with this email already exists")
    return tokens


@router.post("/auth/login")
def login(body: Login, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    # A dummy hash gives missing accounts comparable password-check cost.
    stored = user.password_hash if user else _DUMMY_PASSWORD_HASH
    valid = verify_password(body.password, stored)
    if not user or not valid or not user.active:
        raise HTTPException(401, "Incorrect email or password")
    tokens = issue_tokens(db, user)
    audit(db, user, "auth.login", "user", user.id)
    db.commit()
    return tokens


_DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(24))


@router.post("/auth/refresh")
def refresh(body: TokenBody, db: Session = Depends(get_db)):
    stored = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash(body.refresh_token)).with_for_update())
    if not stored or stored.revoked or aware(stored.expires_at) <= utcnow():
        raise HTTPException(401, "Refresh token expired or revoked")
    user = db.get(User, stored.user_id)
    if not user or not user.active:
        raise HTTPException(401, "Account inactive")
    claimed = db.execute(update(RefreshToken).where(RefreshToken.id == stored.id, RefreshToken.revoked.is_(False)).values(revoked=True))
    if claimed.rowcount != 1:
        raise HTTPException(401, "Refresh token already used")
    tokens = issue_tokens(db, user)
    db.commit()
    return tokens


@router.post("/auth/logout")
def logout(body: TokenBody, user: User = Depends(get_current_user), db: Session = Depends(get_db), credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    if decode_access_token(credentials.credentials)["sid"] != token_hash(body.refresh_token):
        raise HTTPException(401, "Refresh token does not match the current session")
    stored = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash(body.refresh_token), RefreshToken.user_id == user.id))
    if stored:
        stored.revoked = True
    audit(db, user, "auth.logout", "user", user.id)
    db.commit()
    return {"message": "Signed out"}


@router.post("/auth/forgot-password")
def forgot_password(body: ForgotPassword, db: Session = Depends(get_db)):
    if not settings.demo_mode and not recovery_delivery_configured():
        raise HTTPException(503, "Password reset delivery is not configured. Contact the administrator.")
    result = {"message": "If an active account exists, recovery instructions were delivered. In the local demonstration, contact the administrator for the private recovery message."}
    user = db.scalar(select(User).where(User.email == body.email.lower(), User.active.is_(True)))
    if user:
        token = secrets.token_urlsafe(48)
        db.add(PasswordReset(user_id=user.id, token_hash=token_hash(token), expires_at=utcnow() + timedelta(minutes=15)))
        try:
            deliver_reset(db, user, token)
        except (OSError, RuntimeError):
            db.rollback()
            # Keep account existence private even when the delivery service fails.
            return result
        db.commit()
    return result


@router.post("/auth/reset-password")
def reset_password(body: ResetPassword, db: Session = Depends(get_db)):
    stored = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == token_hash(body.token)).with_for_update())
    if not stored or stored.used or aware(stored.expires_at) <= utcnow():
        raise HTTPException(400, "Reset token expired or already used")
    claimed = db.execute(update(PasswordReset).where(PasswordReset.id == stored.id, PasswordReset.used.is_(False)).values(used=True))
    if claimed.rowcount != 1:
        raise HTTPException(400, "Reset token already used")
    user = db.get(User, stored.user_id)
    user.password_hash = hash_password(body.password)
    db.execute(update(PasswordReset).where(PasswordReset.user_id == user.id).values(used=True))
    db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id).values(revoked=True))
    audit(db, user, "auth.password_reset", "user", user.id)
    db.commit()
    return {"message": "Password updated. Sign in again."}
