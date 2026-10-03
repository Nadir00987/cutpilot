"""Render queue: credit check + deduct, RenderJob lifecycle, download, publish stub."""
from __future__ import annotations

import logging
import math
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import auth as auth_lib
from .. import jobs, models
from ..config import settings, storage_root
from ..db import get_db

logger = logging.getLogger("cutpilot.routers.render")

router = APIRouter(tags=["render"])

PRESETS = ("1080p", "4k", "720p", "9:16", "1:1")


class RenderIn(BaseModel):
    preset: str = "1080p"


def _get_owned(db: Session, project_id: str, user: models.User) -> models.Project:
    project = db.get(models.Project, project_id)
    if project is None or (project.user_id != user.id and user.role != "admin"):
        raise HTTPException(404, "Project not found")
    return project


def _job_out(j: models.RenderJob) -> dict:
    return {
        "id": j.id,
        "project_id": j.project_id,
        "preset": j.preset,
        "status": j.status,
        "progress": j.progress,
        "credits_charged": j.credits_charged,
        "error": j.error,
        "created_at": j.created_at.isoformat() if j.created_at else None,
    }


def _deduct_credits(db: Session, user: models.User, amount: float, reason: str) -> None:
    user.credits = round(user.credits - amount, 2)
    db.add(models.CreditTransaction(user_id=user.id, amount=-amount, reason=reason))
    db.commit()


@router.post("/projects/{project_id}/render")
def start_render(
    project_id: str,
    body: RenderIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    if body.preset not in PRESETS:
        raise HTTPException(400, f"Unknown preset {body.preset!r}. Choose from {PRESETS}")
    project = _get_owned(db, project_id, user)
    if not project.source_path:
        raise HTTPException(400, "Upload source media first")
    if not project.duration or project.duration <= 0:
        raise HTTPException(400, "Project has no measurable duration")

    needed = math.ceil(project.duration / 60 * settings.credits_per_minute)
    if user.credits < needed:
        raise HTTPException(
            402,
            f"Insufficient credits: need {needed}, have {user.credits:.2f}. "
            "Top up at /billing.",
        )

    # A project already rendering shouldn't be double-queued.
    busy = (
        db.query(models.RenderJob)
        .filter(
            models.RenderJob.project_id == project_id,
            models.RenderJob.status.in_(("queued", "running")),
        )
        .first()
    )
    if busy:
        raise HTTPException(409, "A render is already queued/running for this project")

    _deduct_credits(db, user, needed, f"render {project_id} preset={body.preset}")
    job = models.RenderJob(
        project_id=project_id, preset=body.preset, status="queued", credits_charged=needed
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    project.status = "rendering"
    db.commit()

    jobs.clear_progress(project_id)
    celery_job_id = jobs.submit_job("render", project_id, {"render_job_id": job.id})
    jobs.report_progress(project_id, "queued", 0, "Render queued", kind="render",
                         render_job_id=job.id)
    out = _job_out(job)
    out["worker_job_id"] = celery_job_id
    return out


@router.get("/renders")
def list_renders(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    q = (
        db.query(models.RenderJob)
        .join(models.Project, models.RenderJob.project_id == models.Project.id)
        .filter(models.Project.user_id == user.id)
        .order_by(models.RenderJob.created_at.desc())
    )
    total = q.count()
    return {"total": total, "items": [_job_out(j) for j in q.offset(offset).limit(limit).all()]}


@router.get("/renders/{render_id}")
def get_render(
    render_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    job = db.get(models.RenderJob, render_id)
    if job is None:
        raise HTTPException(404, "Render not found")
    project = db.get(models.Project, job.project_id)
    if project is None or (project.user_id != user.id and user.role != "admin"):
        raise HTTPException(404, "Render not found")
    return _job_out(job)


@router.get("/renders/{render_id}/download")
def download_render(
    render_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    job = db.get(models.RenderJob, render_id)
    if job is None:
        raise HTTPException(404, "Render not found")
    project = db.get(models.Project, job.project_id)
    if project is None or (project.user_id != user.id and user.role != "admin"):
        raise HTTPException(404, "Render not found")
    if job.status != "done" or not job.output_path:
        raise HTTPException(409, "Render is not ready for download")
    path = storage_root() / job.output_path
    if not path.exists():
        raise HTTPException(404, "Render file missing from storage")
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in project.name).strip() or "project"
    filename = f"{safe_name}_{job.preset}_{date.today().isoformat()}.mp4"
    return FileResponse(path, media_type="video/mp4", filename=filename)


@router.post("/projects/{project_id}/publish/youtube")
def publish_youtube(
    project_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    """Publish hook. The code path is real (auth, ownership, logging);
    the YouTube upload itself is a stub until YOUTUBE_API_KEY is wired."""
    project = _get_owned(db, project_id, user)
    logger.info("youtube publish requested: user=%s project=%s (%s)", user.id, project.id, project.name)
    return {
        "status": "stub",
        "message": "YouTube publish hook — connect YOUTUBE_API_KEY",
        "project_id": project.id,
    }
