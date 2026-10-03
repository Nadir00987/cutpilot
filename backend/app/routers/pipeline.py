"""Pipeline routes: analyze / plan / plan versions / status / shorts / chapters / thumbnails.

Worker C's `app.services.render_pipeline` is imported LAZILY inside handlers:
if it isn't implemented yet, these endpoints return 501 with a clear message —
never crash the API.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import auth as auth_lib
from .. import jobs, models
from ..config import storage_root
from ..db import get_db

logger = logging.getLogger("cutpilot.routers.pipeline")

router = APIRouter(prefix="/projects", tags=["pipeline"])


class PlanIn(BaseModel):
    style: dict[str, Any] = {}
    options: dict[str, Any] = {}


class ApplyTemplateIn(BaseModel):
    template_id: str


def _get_owned(db: Session, project_id: str, user: models.User) -> models.Project:
    project = db.get(models.Project, project_id)
    if project is None or (project.user_id != user.id and user.role != "admin"):
        raise HTTPException(404, "Project not found")
    return project


def _load_analysis_dict(project_id: str) -> dict:
    path = _project_dir(project_id) / "analysis.json"
    if not path.exists():
        raise HTTPException(400, "Run analysis first (POST /projects/{id}/analyze)")
    return json.loads(path.read_text())


def _load_plan_dict(db: Session, project_id: str) -> dict:
    rec = _latest_plan(db, project_id)
    if rec is not None:
        return dict(rec.plan_json)
    path = _project_dir(project_id) / "edit_plan.json"
    if path.exists():
        return json.loads(path.read_text())
    raise HTTPException(400, "Generate an edit plan first (POST /projects/{id}/plan)")


def _service_or_501(module_name: str, fn_name: str):
    """Import app.services.<module_name>.<fn_name>, else 501 (no crash)."""
    try:
        mod = __import__(f"app.services.{module_name}", fromlist=[fn_name])
    except ImportError as e:
        raise HTTPException(501, f"service app.services.{module_name} not available: {e}")
    fn = getattr(mod, fn_name, None)
    if fn is None:
        raise HTTPException(501, f"{fn_name} not implemented in app.services.{module_name}")
    return fn


def _call_service(label: str, fn, *args, **kwargs):
    """Run a downstream service fn; a bug inside it becomes 502, never a raw 500."""
    try:
        return fn(*args, **kwargs)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("%s service failed", label)
        raise HTTPException(502, f"{label} failed: {e}")


def _project_dir(project_id: str) -> Path:
    d = storage_root() / "projects" / project_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _latest_plan(db: Session, project_id: str) -> models.EditPlanVersion | None:
    return (
        db.query(models.EditPlanVersion)
        .filter(models.EditPlanVersion.project_id == project_id)
        .order_by(models.EditPlanVersion.version.desc())
        .first()
    )


def _save_plan_version(
    db: Session, project: models.Project, plan: dict, created_by: str
) -> models.EditPlanVersion:
    latest = _latest_plan(db, project.id)
    version = (latest.version + 1) if latest else 1
    rec = models.EditPlanVersion(
        project_id=project.id, version=version, plan_json=plan, created_by=created_by
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    # Keep edit_plan.json in sync (contract path for other workers).
    (_project_dir(project.id) / "edit_plan.json").write_text(json.dumps(plan, indent=2))
    return rec


def _plan_out(rec: models.EditPlanVersion) -> dict:
    return {
        "version": rec.version,
        "created_by": rec.created_by,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
        "plan": rec.plan_json,
    }


# ------------------------------------------------------------------ analyze
@router.post("/{project_id}/analyze")
def analyze(
    project_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    project = _get_owned(db, project_id, user)
    if not project.source_path:
        raise HTTPException(400, "Upload source media first")
    project.status = "analyzing"
    db.commit()
    jobs.clear_progress(project_id)
    job_id = jobs.submit_job("analyze", project_id, {})
    jobs.report_progress(project_id, "queued", 0, "Analysis queued", kind="analyze")
    return {"job_id": job_id, "status": project.status}


# --------------------------------------------------------------------- plan
@router.post("/{project_id}/plan")
def build_plan(
    project_id: str,
    body: PlanIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    project = _get_owned(db, project_id, user)
    analysis = _project_dir(project_id) / "analysis.json"
    if not analysis.exists():
        raise HTTPException(400, "Run analysis first (POST /analyze)")
    # Worker B's planner expects flat style keys (template_id, kinetic_style, ...).
    style_opts = {**(body.options or {}), **(body.style or {})}
    project.style_opts = style_opts
    project.status = "planning"
    db.commit()
    jobs.clear_progress(project_id)
    job_id = jobs.submit_job("plan", project_id, {"style_opts": style_opts})
    jobs.report_progress(project_id, "queued", 0, "Planning queued", kind="plan")
    return {"job_id": job_id, "status": project.status}


@router.get("/{project_id}/plan")
def get_plan(
    project_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    _get_owned(db, project_id, user)
    rec = _latest_plan(db, project_id)
    if rec is None:
        raise HTTPException(404, "No edit plan yet — POST /plan to generate one")
    return _plan_out(rec)


@router.put("/{project_id}/plan")
def save_plan(
    project_id: str,
    plan: dict[str, Any],
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    """Save a manually edited full edit plan -> new version."""
    project = _get_owned(db, project_id, user)
    rec = _save_plan_version(db, project, plan, created_by=f"user:{user.id}")
    return _plan_out(rec)


@router.get("/{project_id}/plan/versions")
def plan_versions(
    project_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    _get_owned(db, project_id, user)
    recs = (
        db.query(models.EditPlanVersion)
        .filter(models.EditPlanVersion.project_id == project_id)
        .order_by(models.EditPlanVersion.version.desc())
        .all()
    )
    return {
        "versions": [
            {
                "version": r.version,
                "created_by": r.created_by,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in recs
        ]
    }


@router.post("/{project_id}/plan/restore/{version}")
def restore_plan(
    project_id: str,
    version: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    project = _get_owned(db, project_id, user)
    rec = (
        db.query(models.EditPlanVersion)
        .filter(
            models.EditPlanVersion.project_id == project_id,
            models.EditPlanVersion.version == version,
        )
        .first()
    )
    if rec is None:
        raise HTTPException(404, "Plan version not found")
    restored = _save_plan_version(
        db, project, rec.plan_json, created_by=f"restore:{version}"
    )
    return _plan_out(restored)


# ------------------------------------------------------------------- status
@router.get("/{project_id}/status")
def project_status(
    project_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    project = _get_owned(db, project_id, user)
    return {
        "project_id": project.id,
        "status": project.status,
        "progress": jobs.get_progress(project_id),
    }


# ------------------------------------------------------------------- shorts
@router.get("/{project_id}/shorts")
def shorts_candidates(
    project_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    _get_owned(db, project_id, user)
    # Contract first: render_pipeline.shorts_candidates(project_id);
    # Worker C split it into app.services.shorts(analysis, plan) — adapt.
    try:
        from ..services import render_pipeline as rp

        fn = getattr(rp, "shorts_candidates", None)
        if fn is not None:
            return {"candidates": fn(project_id)}
    except ImportError:
        pass
    sc = _service_or_501("shorts", "shorts_candidates")
    analysis = _load_analysis_dict(project_id)
    plan = _load_plan_dict(db, project_id)
    return {"candidates": _call_service("shorts_candidates", sc, analysis, plan)}


def _progress_cb_for(project_id: str, kind: str):
    """Adapter: service cbs call cb(stage, pct, eta) -> our report_progress."""
    def cb(stage, pct, eta=None):
        message = str(stage)
        if isinstance(eta, (int, float)) and eta:
            message = f"{stage} — ETA {eta:.0f}s"
        jobs.report_progress(project_id, str(stage), float(pct or 0), message, kind=kind)

    return cb


@router.post("/{project_id}/shorts/extract")
async def shorts_extract(
    project_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    _get_owned(db, project_id, user)
    cb = _progress_cb_for(project_id, "shorts")
    try:
        from ..services import render_pipeline as rp

        fn = getattr(rp, "extract_shorts", None)
        if fn is not None:
            try:
                result = await asyncio.to_thread(fn, project_id, cb)
            except Exception as e:
                logger.exception("extract_shorts service failed")
                raise HTTPException(502, f"extract_shorts failed: {e}")
            return {"result": result}
    except ImportError:
        pass
    ex = _service_or_501("shorts", "extract_shorts")
    try:
        result = await asyncio.to_thread(ex, project_id, cb)
    except Exception as e:
        logger.exception("extract_shorts service failed")
        raise HTTPException(502, f"extract_shorts failed: {e}")
    return {"result": result}


# ------------------------------------------------------------------ chapters
@router.get("/{project_id}/chapters")
def get_chapters(
    project_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    _get_owned(db, project_id, user)
    try:
        from ..services import render_pipeline as rp

        fn = getattr(rp, "get_chapters", None)
        if fn is not None:
            return {"chapters": _call_service("get_chapters", fn, project_id)}
    except ImportError:
        pass
    gc = _service_or_501("chapters", "get_chapters")
    analysis = _load_analysis_dict(project_id)
    text, chapters = _call_service("get_chapters", gc, analysis)
    return {"chapters": chapters, "text": text}


# --------------------------------------------------------------- thumbnails
@router.get("/{project_id}/thumbnails")
def list_thumbnails(
    project_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    _get_owned(db, project_id, user)
    tdir = storage_root() / "thumbnails" / project_id
    items = []
    if tdir.exists():
        for p in sorted(tdir.glob("thumb_*.png")):
            items.append({"url": f"/storage/thumbnails/{project_id}/{p.name}", "name": p.name})
    return {"thumbnails": items}


@router.post("/{project_id}/thumbnails/generate")
async def generate_thumbnails(
    project_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    _get_owned(db, project_id, user)
    analysis = _load_analysis_dict(project_id)
    try:
        from ..services import render_pipeline as rp

        fn = getattr(rp, "generate_thumbnails", None)
        if fn is not None:
            try:
                try:
                    result = await asyncio.to_thread(fn, project_id, analysis)
                except TypeError:
                    result = await asyncio.to_thread(fn, project_id)
            except Exception as e:
                logger.exception("generate_thumbnails service failed")
                raise HTTPException(502, f"generate_thumbnails failed: {e}")
            return {"result": result}
    except ImportError:
        pass
    gt = _service_or_501("thumbnails", "generate_thumbnails")
    try:
        try:
            result = await asyncio.to_thread(gt, project_id, analysis)
        except TypeError:
            result = await asyncio.to_thread(gt, project_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("generate_thumbnails service failed")
        raise HTTPException(502, f"generate_thumbnails failed: {e}")
    return {"result": result}
