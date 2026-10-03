"""Admin routes (role=admin only): users, jobs, system health, worker status."""
from __future__ import annotations

import logging
import shutil
import subprocess

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import auth as auth_lib
from .. import jobs, models
from ..config import settings, storage_root
from ..db import get_db

logger = logging.getLogger("cutpilot.routers.admin")

router = APIRouter(prefix="/admin", tags=["admin"])

Admin = Depends(auth_lib.get_current_admin)


@router.get("/users")
def list_users(limit: int = 50, offset: int = 0, db: Session = Depends(get_db), _=Admin):
    q = db.query(models.User).order_by(models.User.created_at.desc())
    total = q.count()
    items = q.offset(offset).limit(limit).all()
    return {
        "total": total,
        "items": [
            {
                "id": u.id,
                "email": u.email,
                "name": u.name,
                "role": u.role,
                "credits": u.credits,
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in items
        ],
    }


@router.get("/jobs")
def list_jobs(limit: int = 50, offset: int = 0, db: Session = Depends(get_db), _=Admin):
    q = (
        db.query(models.RenderJob, models.Project.name)
        .join(models.Project, models.RenderJob.project_id == models.Project.id)
        .order_by(models.RenderJob.created_at.desc())
    )
    total = q.count()
    items = []
    for job, pname in q.offset(offset).limit(limit).all():
        items.append({
            "id": job.id,
            "project_id": job.project_id,
            "project_name": pname,
            "preset": job.preset,
            "status": job.status,
            "progress": job.progress,
            "credits_charged": job.credits_charged,
            "error": job.error,
            "created_at": job.created_at.isoformat() if job.created_at else None,
        })
    return {"total": total, "items": items}


def _ffmpeg_version() -> str:
    try:
        out = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, timeout=5
        )
        return out.stdout.splitlines()[0] if out.stdout else "unknown"
    except Exception as e:
        return f"unavailable ({e})"


def _whisper_info() -> dict:
    try:
        import faster_whisper  # noqa: F401

        return {"installed": True, "model": settings.whisper_model}
    except ImportError:
        return {"installed": False, "model": settings.whisper_model}


@router.get("/health")
def health(db: Session = Depends(get_db), _=Admin):
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        db_ok = False
        logger.warning("db health check failed: %s", e)
    disk = shutil.disk_usage(storage_root())
    return {
        "status": "ok" if db_ok else "degraded",
        "ffmpeg": _ffmpeg_version(),
        "whisper": _whisper_info(),
        "redis": {"reachable": jobs.redis_available(), "url": settings.redis_url},
        "database": {"ok": db_ok, "url": settings.database_url.split("@")[-1]},
        "storage": {
            "root": str(storage_root()),
            "free_gb": round(disk.free / 1e9, 2),
            "total_gb": round(disk.total / 1e9, 2),
        },
        "worker_mode": jobs.worker_mode(),
    }


@router.get("/workers")
def workers(_=Admin):
    registered = []
    if jobs.celery_app is not None:
        registered = sorted(jobs.celery_app.tasks.keys())
    return {
        "mode": jobs.worker_mode(),
        "celery_tasks": registered,
        "in_process_jobs": {
            jid: {"kind": j.get("kind"), "status": j.get("status")}
            for jid, j in jobs._jobs.items()
            if j.get("mode") == "in-process"
        },
    }
