"""Extra tables for CutPilot AI: teams, comments, batch jobs.

Import-safe by design (Worker A does `try: import app.models_extras`):
- If Worker A's `app.models` already defines any of these tables, we simply
  re-export them instead of redefining (avoids duplicate-table errors).
- If `app.models` (or its `Base`) is not importable yet, we fall back to a
  local `declarative_base()` so this module still imports cleanly.
"""
from __future__ import annotations

import datetime as _dt

try:  # Worker A core models (preferred source of Base + tables)
    from app import models as _core_models
    Base = _core_models.Base
except Exception:  # pragma: no cover - core not present yet
    from sqlalchemy.orm import declarative_base

    Base = declarative_base()
    _core_models = None

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column


def _core(name: str):
    """Return Worker A's table class if it already defined one."""
    return getattr(_core_models, name, None) if _core_models is not None else None


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


# ------------------------------------------------------------------ Team
if _core("Team") is not None:
    Team = _core("Team")
else:

    class Team(Base):
        __tablename__ = "teams"

        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        name: Mapped[str] = mapped_column(String(120), nullable=False)
        owner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
        created_at: Mapped[_dt.datetime] = mapped_column(
            DateTime(timezone=True), default=_utcnow, nullable=False
        )


# ------------------------------------------------------------ TeamMember
if _core("TeamMember") is not None:
    TeamMember = _core("TeamMember")
else:

    class TeamMember(Base):
        __tablename__ = "team_members"

        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        team_id: Mapped[int] = mapped_column(
            Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
        )
        user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
        role: Mapped[str] = mapped_column(String(20), default="editor", nullable=False)
        joined_at: Mapped[_dt.datetime] = mapped_column(
            DateTime(timezone=True), default=_utcnow, nullable=False
        )


# ------------------------------------------------------------ TeamInvite
if _core("TeamInvite") is not None:
    TeamInvite = _core("TeamInvite")
else:

    class TeamInvite(Base):
        __tablename__ = "team_invites"

        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        team_id: Mapped[int] = mapped_column(
            Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
        )
        email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
        role: Mapped[str] = mapped_column(String(20), default="viewer", nullable=False)
        token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
        accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
        expires_at: Mapped[_dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
        created_at: Mapped[_dt.datetime] = mapped_column(
            DateTime(timezone=True), default=_utcnow, nullable=False
        )


# --------------------------------------------------------------- Comment
if _core("Comment") is not None:
    Comment = _core("Comment")
else:

    class Comment(Base):
        """A comment pinned to a timeline timestamp on a project."""

        __tablename__ = "comments"

        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
        user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
        timestamp: Mapped[float] = mapped_column(Float, nullable=False)  # source seconds
        text: Mapped[str] = mapped_column(Text, nullable=False)
        resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
        created_at: Mapped[_dt.datetime] = mapped_column(
            DateTime(timezone=True), default=_utcnow, nullable=False
        )


# -------------------------------------------------------------- BatchJob
if _core("BatchJob") is not None:
    BatchJob = _core("BatchJob")
else:

    class BatchJob(Base):
        """One batch run: same style preset applied to many projects."""

        __tablename__ = "batch_jobs"

        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
        project_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
        preset: Mapped[str] = mapped_column(String(40), default="1080p", nullable=False)
        style: Mapped[str] = mapped_column(String(80), default="default", nullable=False)
        status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
        progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
        result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
        created_at: Mapped[_dt.datetime] = mapped_column(
            DateTime(timezone=True), default=_utcnow, nullable=False
        )
        finished_at: Mapped[_dt.datetime | None] = mapped_column(
            DateTime(timezone=True), nullable=True
        )


__all__ = ["Base", "Team", "TeamMember", "TeamInvite", "Comment", "BatchJob"]
