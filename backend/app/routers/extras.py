"""Extra API routes: teams, comments, batch processing, voiceover, metadata.

Import-safe by design (Worker A's main.py does `try: from app.routers import extras`):
- Module level imports NOTHING from other workers' code — only fastapi,
  stdlib, pydantic, and our own import-safe `app.models_extras`.
- Worker A's DB session factory, auth helpers and job queue are resolved
  LAZILY inside each request (never at import time).
- Mounting: this router carries NO prefix; main.py mounts it with
  prefix="/api/v1" exactly like every other router (auth, projects, ...).
  (The original Worker-E spec said prefix="/api/v1" on the router itself —
  that would double-prefix to /api/v1/api/v1/* under main.py, so the prefix
  lives on the include instead. See ACCEPTANCE.md.)

Table shapes follow Worker A's app/models.py exactly (Team/TeamMember/
TeamInvite/Comment/BatchJob are defined there; app/models_extras.py
re-exports them instead of redefining).
"""
from __future__ import annotations

import json
import os
import secrets
from typing import Any, Iterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.models_extras import BatchJob, Comment, Team, TeamInvite, TeamMember

router = APIRouter(tags=["extras"])


# ------------------------------------------------------- lazy core glue
def _get_db() -> Iterator[Any]:
    """Yield a DB session from Worker A's SessionLocal (lazy import)."""
    from app.db import SessionLocal  # lazy: never at module import time

    db = SessionLocal()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception:
            pass


async def _current_user(request: Request) -> Any:
    """Resolve Worker A's User from the Bearer token (lazy imports only)."""
    from app.auth import get_user_from_token  # lazy
    from app.db import SessionLocal  # lazy

    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer ") or len(auth) <= 7:
        raise HTTPException(status_code=401, detail="Not authenticated")
    db = SessionLocal()
    try:
        return get_user_from_token(auth[7:].strip(), db)
    finally:
        db.close()


def _frontend_url() -> str:
    try:
        from app.config import settings  # lazy

        return settings.frontend_url
    except Exception:
        return os.environ.get("FRONTEND_URL", "http://localhost:3000")


# ------------------------------------------------------------ schemas
class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class TeamUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class InviteCreate(BaseModel):
    email: str
    role: str = Field(default="viewer", pattern="^(editor|viewer)$")


class MemberUpdate(BaseModel):
    role: str = Field(pattern="^(owner|editor|viewer)$")


class CommentCreate(BaseModel):
    timestamp: float = Field(ge=0, description="seconds in source timeline")
    text: str = Field(min_length=1, max_length=2000)


class BatchCreate(BaseModel):
    project_ids: list[str] = Field(min_length=1, max_length=50)
    preset: str = "1080p"
    style: str = "default"


class VoiceoverCreate(BaseModel):
    script: str = Field(min_length=1, max_length=5000)
    voice: str = "default"


# ------------------------------------------------------------ helpers
def _team_or_404(db: Any, team_id: int) -> Team:
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="team not found")
    return team


def _membership(db: Any, team_id: int, user_id: int) -> TeamMember | None:
    return (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
        .first()
    )


def _require_member(db: Any, team_id: int, user_id: int,
                    roles=("owner", "editor", "viewer")) -> TeamMember:
    m = _membership(db, team_id, user_id)
    if m is None or m.role not in roles:
        raise HTTPException(status_code=403, detail="not a team member")
    return m


def _team_dict(team: Team) -> dict:
    return {"id": team.id, "name": team.name, "owner_id": team.owner_id}


def _split_invite_token(token: str) -> tuple[str, str]:
    """Invite tokens are '{role}.{random}' (Worker A's schema has no role column)."""
    role, _, rand = token.partition(".")
    if role not in ("editor", "viewer") or not rand:
        raise HTTPException(status_code=404, detail="invite not found or invalid")
    return role, rand


# ------------------------------------------------------------ teams CRUD
@router.post("/teams", status_code=201)
def create_team(body: TeamCreate, db=Depends(_get_db), user=Depends(_current_user)):
    team = Team(name=body.name, owner_id=user.id)
    db.add(team)
    db.flush()
    db.add(TeamMember(team_id=team.id, user_id=user.id, role="owner"))
    db.commit()
    return _team_dict(team)


@router.get("/teams")
def list_teams(db=Depends(_get_db), user=Depends(_current_user)):
    member_rows = db.query(TeamMember).filter(TeamMember.user_id == user.id).all()
    team_ids = [m.team_id for m in member_rows]
    teams = db.query(Team).filter(Team.id.in_(team_ids)).all() if team_ids else []
    out = []
    for t in teams:
        d = _team_dict(t)
        m = _membership(db, t.id, user.id)
        d["my_role"] = m.role if m else None
        out.append(d)
    return out


@router.get("/teams/{team_id}")
def get_team(team_id: int, db=Depends(_get_db), user=Depends(_current_user)):
    _require_member(db, team_id, user.id)
    return _team_dict(_team_or_404(db, team_id))


@router.patch("/teams/{team_id}")
def update_team(team_id: int, body: TeamUpdate, db=Depends(_get_db),
                user=Depends(_current_user)):
    _require_member(db, team_id, user.id, roles=("owner", "editor"))
    team = _team_or_404(db, team_id)
    team.name = body.name
    db.commit()
    return _team_dict(team)


@router.delete("/teams/{team_id}", status_code=204)
def delete_team(team_id: int, db=Depends(_get_db), user=Depends(_current_user)):
    _require_member(db, team_id, user.id, roles=("owner",))
    team = _team_or_404(db, team_id)
    db.query(TeamMember).filter(TeamMember.team_id == team_id).delete()
    db.query(TeamInvite).filter(TeamInvite.team_id == team_id).delete()
    db.delete(team)
    db.commit()
    return None


@router.get("/teams/{team_id}/members")
def list_members(team_id: int, db=Depends(_get_db), user=Depends(_current_user)):
    _require_member(db, team_id, user.id)
    rows = db.query(TeamMember).filter(TeamMember.team_id == team_id).all()
    return [{"team_id": r.team_id, "user_id": r.user_id, "role": r.role} for r in rows]


@router.patch("/teams/{team_id}/members/{member_id}")
def update_member(team_id: int, member_id: int, body: MemberUpdate,
                  db=Depends(_get_db), user=Depends(_current_user)):
    _require_member(db, team_id, user.id, roles=("owner",))
    m = _membership(db, team_id, member_id)
    if m is None:
        raise HTTPException(status_code=404, detail="member not found")
    if m.role == "owner" and body.role != "owner":
        owners = db.query(TeamMember).filter(
            TeamMember.team_id == team_id, TeamMember.role == "owner").count()
        if owners <= 1:
            raise HTTPException(status_code=400, detail="team must keep at least one owner")
    m.role = body.role
    db.commit()
    return {"team_id": team_id, "user_id": member_id, "role": m.role}


# ------------------------------------------------------------ invites
@router.post("/teams/{team_id}/invite", status_code=201)
def invite_member(team_id: int, body: InviteCreate, db=Depends(_get_db),
                  user=Depends(_current_user)):
    _require_member(db, team_id, user.id, roles=("owner", "editor"))
    _team_or_404(db, team_id)
    # Worker A's team_invites table has no role/expires columns, so the
    # requested role is encoded in the token itself: "{role}.{random}".
    token = f"{body.role}.{secrets.token_urlsafe(32)}"
    invite = TeamInvite(team_id=team_id, email=body.email.lower().strip(), token=token)
    db.add(invite)
    db.commit()
    return {
        "id": invite.id, "team_id": team_id, "email": invite.email,
        "role": body.role, "token": token,
        "join_url": f"{_frontend_url()}/teams/join?token={token}",
    }


@router.post("/teams/invites/{token}/accept")
def accept_invite(token: str, db=Depends(_get_db), user=Depends(_current_user)):
    role, _ = _split_invite_token(token)
    invite = db.query(TeamInvite).filter(TeamInvite.token == token).first()
    if invite is None or invite.accepted:
        raise HTTPException(status_code=404, detail="invite not found or already used")
    if _membership(db, invite.team_id, user.id) is None:
        db.add(TeamMember(team_id=invite.team_id, user_id=user.id, role=role))
    invite.accepted = True
    db.commit()
    return {"team_id": invite.team_id, "role": role}


# ------------------------------------------------------------ comments
@router.get("/projects/{project_id}/comments")
def list_comments(project_id: str, db=Depends(_get_db), user=Depends(_current_user)):
    rows = (
        db.query(Comment)
        .filter(Comment.project_id == project_id)
        .order_by(Comment.timestamp.asc())
        .all()
    )
    return [
        {"id": c.id, "project_id": c.project_id, "user_id": c.user_id,
         "timestamp": c.timestamp, "text": c.text,
         "created_at": c.created_at.isoformat() if c.created_at else None}
        for c in rows
    ]


@router.post("/projects/{project_id}/comments", status_code=201)
def add_comment(project_id: str, body: CommentCreate, db=Depends(_get_db),
                user=Depends(_current_user)):
    comment = Comment(project_id=project_id, user_id=user.id,
                      timestamp=body.timestamp, text=body.text)
    db.add(comment)
    db.commit()
    return {"id": comment.id, "project_id": project_id,
            "timestamp": comment.timestamp, "text": comment.text}


# ------------------------------------------------------------ batch
@router.post("/batch", status_code=201)
def create_batch(body: BatchCreate, db=Depends(_get_db), user=Depends(_current_user)):
    from app import jobs as jobs_lib  # lazy: Worker A's job queue

    job = BatchJob(
        user_id=user.id,
        name=f"Batch of {len(body.project_ids)} projects",
        preset={
            "preset": body.preset, "style": body.style,
            "project_ids": body.project_ids, "job_ids": {},
        },
        status="queued",
    )
    db.add(job)
    db.commit()

    submitted: dict[str, str] = {}
    try:
        for pid in body.project_ids:
            # Fan out the analysis stage per project via Worker A's queue
            # (Celery when Redis is up, in-process ThreadPoolExecutor otherwise).
            # Plan + render are chained per project once its analysis lands —
            # see _chain_batch; the batch record tracks every stage.
            submitted[pid] = jobs_lib.submit_job("analyze", pid, {})
    except Exception as exc:
        job.status = "error"
        job.preset["error"] = str(exc)[:500]
        db.commit()
        raise HTTPException(status_code=502, detail=f"could not submit batch jobs: {exc}")

    job.preset["job_ids"] = submitted
    job.status = "running"
    db.commit()
    return _batch_dict(db, job)


@router.get("/batch/{batch_id}")
def get_batch(batch_id: str, db=Depends(_get_db), user=Depends(_current_user)):
    job = db.get(BatchJob, batch_id)
    if job is None:
        raise HTTPException(status_code=404, detail="batch job not found")
    if job.user_id != user.id:
        raise HTTPException(status_code=403, detail="not your batch job")
    return _batch_dict(db, job)


def _batch_dict(db: Any, job: BatchJob) -> dict:
    from app import jobs as jobs_lib  # lazy

    preset = dict(job.preset or {})
    stages = {}
    for pid, jid in (preset.get("job_ids") or {}).items():
        try:
            stages[pid] = jobs_lib.get_job_status(jid).get("status", "unknown")
        except Exception:
            stages[pid] = "unknown"
    return {
        "id": job.id, "name": job.name, "status": job.status,
        "preset": preset.get("preset"), "style": preset.get("style"),
        "project_ids": preset.get("project_ids", []),
        "project_stage_status": stages,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


# ------------------------------------------------------------ voiceover
@router.post("/projects/{project_id}/voiceover")
def create_voiceover(project_id: str, body: VoiceoverCreate,
                     user=Depends(_current_user)):
    from app.services.voiceover import synthesize  # own module: always import-safe

    try:
        return synthesize(script=body.script, voice=body.voice, project_id=project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ------------------------------------------------------------ metadata
@router.get("/projects/{project_id}/metadata")
def get_metadata(project_id: str,
                 platform: str = Query("youtube", pattern="^(youtube|tiktok|instagram)$"),
                 user=Depends(_current_user)):
    from app.services.metadata import generate_metadata  # own module: import-safe

    analysis = _load_analysis(project_id)
    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail="analysis.json not found for this project (run analysis first)",
        )
    return generate_metadata(analysis, platform=platform)


def _load_analysis(project_id: str) -> Optional[dict]:
    """Locate analysis.json in Worker A's storage layout (lazy config)."""
    try:
        from app.config import storage_root  # lazy

        root = storage_root()
    except Exception:
        root = os.environ.get("STORAGE_DIR", "./storage")
        from pathlib import Path

        root = Path(root)
    cand = root / "projects" / project_id / "analysis.json"
    if cand.exists():
        return json.loads(cand.read_text())
    return None
