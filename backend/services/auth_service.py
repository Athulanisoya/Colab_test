"""Session issuance and safe account projection."""
import secrets
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlencode
from datetime import timedelta

import jwt
from sqlalchemy.orm import Session
from sqlalchemy import delete, select

from backend.config import settings
from backend.models.user import RefreshToken, User, utcnow, RoleRecord, UserRole, RecoveryMail
from backend.models.team import TeamMember
from backend.utils.security import token_hash


def serialize_user(user: User):
    return {key: getattr(user, key) for key in ("id", "name", "email", "role", "district", "team_id", "active")}


def issue_tokens(db: Session, user: User):
    sync_account_membership(db, user)
    refresh = secrets.token_urlsafe(48)
    session_key = token_hash(refresh)
    db.add(RefreshToken(token_hash=session_key, user_id=user.id, expires_at=utcnow() + timedelta(days=settings.refresh_token_days)))
    token = jwt.encode({
        "sub": str(user.id), "sid": session_key, "type": "access",
        "iat": utcnow(), "exp": utcnow() + timedelta(minutes=settings.access_token_minutes),
    }, settings.jwt_secret, algorithm="HS256")
    return {"access_token": token, "refresh_token": refresh, "token_type": "bearer", "user": serialize_user(user)}


def sync_account_membership(db, user):
    """Keep normalized authorization/member relations aligned with account changes."""
    db.flush()
    role = db.scalar(select(RoleRecord).where(RoleRecord.name == user.role))
    if not role:
        role = RoleRecord(name=user.role)
        db.add(role)
        db.flush()
    db.execute(delete(UserRole).where(UserRole.user_id == user.id, UserRole.role_id != role.id))
    if not db.get(UserRole, (user.id, role.id)):
        db.add(UserRole(user_id=user.id, role_id=role.id))
    db.execute(delete(TeamMember).where(TeamMember.user_id == user.id, TeamMember.team_id != (user.team_id or -1)))
    if user.role == "response_team" and user.team_id and not db.get(TeamMember, (user.id, user.team_id)):
        db.add(TeamMember(user_id=user.id, team_id=user.team_id))


def recovery_delivery_configured():
    return bool(settings.smtp_host and settings.smtp_from)


def deliver_reset(db, user, token):
    reset_url = settings.frontend_url.rstrip("/") + "/#/reset?" + urlencode({"token": token})
    if recovery_delivery_configured():
        message = EmailMessage()
        message["From"] = settings.smtp_from
        message["To"] = user.email
        message["Subject"] = "ResQ Kerala password recovery"
        message.set_content("Open this private link to reset your password within 15 minutes:\n" + reset_url + "\nIf you did not request this, ignore this email.")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            if settings.smtp_tls:
                server.starttls(context=ssl.create_default_context())
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)
        return "smtp"
    if not settings.demo_mode:
        raise RuntimeError("Recovery delivery is not configured")
    db.add(RecoveryMail(user_id=user.id, recipient=user.email, subject="ResQ Kerala password recovery", reset_url=reset_url))
    return "admin_mailbox"
