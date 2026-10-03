"""Auth: password hashing (bcrypt), JWT access/refresh tokens, dependencies,
password-reset token helpers."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from . import models
from .config import settings
from .db import get_db

ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# ---------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


# ------------------------------------------------------------------- tokens
def _encode(payload: dict) -> str:
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def create_access_token(user_id: int) -> str:
    exp = datetime.utcnow() + timedelta(minutes=settings.access_token_minutes)
    return _encode({"sub": str(user_id), "type": "access", "exp": exp})


def create_refresh_token(user_id: int) -> str:
    exp = datetime.utcnow() + timedelta(days=settings.refresh_token_days)
    return _encode({"sub": str(user_id), "type": "refresh", "exp": exp})


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


def get_user_from_token(token: str, db: Session) -> models.User:
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user = db.get(models.User, int(user_id))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> models.User:
    return get_user_from_token(token, db)


def get_current_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ------------------------------------------------------- password reset
RESET_TOKEN_TTL = timedelta(hours=1)


def create_password_reset_token(db: Session, user: models.User) -> str:
    """Create a reset token; returns the RAW token (only the sha256 is stored)."""
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    rec = models.PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.utcnow() + RESET_TOKEN_TTL,
        used=False,
    )
    db.add(rec)
    db.commit()
    return raw


def consume_password_reset_token(db: Session, raw_token: str) -> models.User | None:
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    rec = (
        db.query(models.PasswordResetToken)
        .filter(models.PasswordResetToken.token_hash == token_hash)
        .first()
    )
    if not rec or rec.used or rec.expires_at < datetime.utcnow():
        return None
    rec.used = True
    db.commit()
    return db.get(models.User, rec.user_id)
