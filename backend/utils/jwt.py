"""JWT decoding and authenticated session validation."""
from datetime import datetime, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database.connection import get_db
from backend.models.user import RefreshToken, User, utcnow

bearer = HTTPBearer(auto_error=False)


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def decode_access_token(token: str):
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], options={"require": ["exp", "sub", "sid", "type"]})


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)):
    unauthorized = HTTPException(401, "Please sign in", headers={"WWW-Authenticate": "Bearer"})
    if not credentials or credentials.scheme.lower() != "bearer":
        raise unauthorized
    try:
        payload = decode_access_token(credentials.credentials)
        if payload["type"] != "access":
            raise unauthorized
        user = db.get(User, int(payload["sub"]))
        session = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == payload["sid"]))
        if not user or not user.active or not session or session.user_id != user.id or session.revoked or aware(session.expires_at) <= utcnow():
            raise unauthorized
        return user
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        raise unauthorized
