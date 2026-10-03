"""Auth routes: signup / login / refresh / forgot-password / reset / me."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from .. import auth as auth_lib
from .. import models
from ..config import settings
from ..db import get_db

logger = logging.getLogger("cutpilot.routers.auth")

router = APIRouter(prefix="/auth", tags=["auth"])


class SignupIn(BaseModel):
    email: EmailStr
    password: str
    name: str = ""


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    role: str
    credits: float
    is_active: bool

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut | None = None


class RefreshIn(BaseModel):
    refresh_token: str


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str
    new_password: str


def _tokens(user: models.User) -> TokenOut:
    return TokenOut(
        access_token=auth_lib.create_access_token(user.id),
        refresh_token=auth_lib.create_refresh_token(user.id),
        user=UserOut.model_validate(user),
    )


@router.post("/signup", response_model=TokenOut, status_code=201)
def signup(body: SignupIn, db: Session = Depends(get_db)):
    if len(body.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    existing = db.query(models.User).filter(models.User.email == body.email.lower()).first()
    if existing:
        raise HTTPException(400, "An account with this email already exists")
    user = models.User(
        email=body.email.lower(),
        password_hash=auth_lib.hash_password(body.password),
        name=body.name.strip(),
        role="user",
        credits=5.0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _tokens(user)


@router.post("/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form.username.lower()).first()
    if not user or not auth_lib.verify_password(form.password, user.password_hash):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(403, "Account is deactivated")
    return _tokens(user)


@router.post("/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    payload = auth_lib.decode_token(body.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(401, "Not a refresh token")
    user = db.get(models.User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(401, "User not found or inactive")
    return _tokens(user)


@router.post("/forgot-password")
def forgot_password(body: ForgotIn, db: Session = Depends(get_db)):
    # Never reveal whether the email exists.
    user = db.query(models.User).filter(models.User.email == body.email.lower()).first()
    if user:
        raw = auth_lib.create_password_reset_token(db, user)
        link = f"{settings.frontend_url}/auth/reset?token={raw}"
        if settings.email_provider == "console":
            # Dev: the "email" is the server log. Real SMTP can be wired later.
            print(f"[console-email] to={user.email} password-reset: {link}", flush=True)
            logger.info("password reset link for %s: %s", user.email, link)
    return {"detail": "If an account exists for this email, a reset link was sent."}


@router.post("/reset-password")
def reset_password(body: ResetIn, db: Session = Depends(get_db)):
    if len(body.new_password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    user = auth_lib.consume_password_reset_token(db, body.token)
    if not user:
        raise HTTPException(400, "Invalid or expired reset token")
    user.password_hash = auth_lib.hash_password(body.new_password)
    db.commit()
    return {"detail": "Password has been reset. You can log in now."}


@router.get("/me", response_model=UserOut)
def me(user: models.User = Depends(auth_lib.get_current_user)):
    return user
