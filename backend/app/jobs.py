"""Job abstraction: Celery+Redis when Redis is reachable, otherwise an automatic
in-process ThreadPoolExecutor fallback. Both paths run the same worker functions.

Contract for other workers:
    celery_app                    -> celery.Celery | None  (None in fallback mode)
    run_analysis_task(project_id) -> celery task, lazily imports
                                     app.services.analysis_pipeline.run_analysis
    run_plan_task(project_id, style_opts)
    run_render_task(render_job_id, project_id=None)

    submit_job(kind, project_id, payload) -> job_id (str)
        kind in {"analyze", "plan", "render"}; payload is a plain dict.
    get_job_status(job_id) -> dict
    report_progress(project_id, stage, pct, message, ...) -> None
        Also publishes to Redis pub/sub channel cutpilot:progress:{project_id}
        and updates the in-memory progress dict (always) + RenderJob.progress.
    get_progress(project_id) -> dict | None  (what the WebSocket polls)
"""
from __future__ import annotations

import json
import logging
import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from .config import settings

logger = logging.getLogger("cutpilot.jobs")

# ---------------------------------------------------------------- state
_progress: dict[str, dict] = {}
_progress_lock = threading.Lock()
_jobs: dict[str, dict] = {}  # fallback-mode registry (+ celery submit records)
_redis_ok: bool | None = None
_redis_ok_ts: float = 0.0
_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


# ------------------------------------------------------- redis reachability
def redis_available(refresh: bool = False) -> bool:
    """1s-timeout socket test against REDIS_URL. Result cached for 60s."""
    global _redis_ok, _redis_ok_ts
    now = time.time()
    if not refresh and _redis_ok is not None and (now - _redis_ok_ts) < 60:
        return _redis_ok
    try:
        u = urlparse(settings.redis_url)
        host = u.hostname or "localhost"
        port = u.port or 6379
        with socket.create_connection((host, port), timeout=1):
            pass
        _redis_ok = True
    except Exception as e:
        logger.warning("Redis unreachable at %s (%s) — using in-process executor", settings.redis_url, e)
        _redis_ok = False
    _redis_ok_ts = now
    return _redis_ok


def _redis_client():
    import redis

    return redis.Redis.from_url(settings.redis_url, socket_timeout=2)


# --------------------------------------------------------------- progress
def report_progress(
    project_id: str,
    stage: str,
    pct: float,
    message: str,
    kind: str | None = None,
    render_job_id: str | None = None,
) -> None:
    entry = {
        "project_id": project_id,
        "stage": stage,
        "pct": float(pct),
        "message": message,
        "ts": time.time(),
    }
    with _progress_lock:
        _progress[project_id] = entry

    # Redis pub/sub for cross-process (celery worker -> web) progress.
    if redis_available():
        try:
            _redis_client().publish(f"cutpilot:progress:{project_id}", json.dumps(entry))
        except Exception as e:
            logger.debug("redis publish failed: %s", e)

    # DB progress for render jobs (best effort — never break the pipeline).
    try:
        from . import models
        from .db import SessionLocal

        db = SessionLocal()
        try:
            job = None
            if render_job_id:
                job = db.get(models.RenderJob, render_job_id)
            elif kind == "render":
                job = (
                    db.query(models.RenderJob)
                    .filter(
                        models.RenderJob.project_id == project_id,
                        models.RenderJob.status.in_(("queued", "running")),
                    )
                    .order_by(models.RenderJob.created_at.desc())
                    .first()
                )
            if job is not None:
                job.progress = float(pct)
                db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.debug("progress db update failed: %s", e)


def get_progress(project_id: str) -> dict | None:
    with _progress_lock:
        return dict(_progress[project_id]) if project_id in _progress else None


def clear_progress(project_id: str) -> None:
    with _progress_lock:
        _progress.pop(project_id, None)


# ------------------------------------------------------- worker functions
# These are the single implementations used by BOTH celery tasks and the
# in-process executor. They own the DB session and status transitions, and
# ADAPT between this layer's stable contract and the service modules'
# actual signatures (Worker B/C):
#   analysis_pipeline.run_analysis(project_id, progress_cb)   cb(pct, stage)
#   planner.build_edit_plan(analysis, style_opts, progress_cb) cb(pct, stage) -> plan dict
#   render_pipeline.run_render(project_id, preset, plan, progress_cb, output_name=None)
#                                                             cb(stage, pct, eta) -> out path
import json as _json
import os as _os


def _set_project_status(project_id: str, status: str) -> None:
    try:
        from . import models
        from .db import SessionLocal

        db = SessionLocal()
        try:
            p = db.get(models.Project, project_id)
            if p:
                p.status = status
                db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.debug("status update failed: %s", e)


def _project_file(project_id: str, name: str):
    from .config import storage_root as _sr

    return _sr() / "projects" / project_id / name


def _load_analysis(project_id: str) -> dict:
    path = _project_file(project_id, "analysis.json")
    if not path.exists():
        raise FileNotFoundError(f"analysis.json not found for project {project_id}")
    return _json.loads(path.read_text())


def _load_plan(project_id: str) -> dict | None:
    """Latest edit plan: EditPlanVersion row first, edit_plan.json fallback."""
    from . import models
    from .db import SessionLocal

    db = SessionLocal()
    try:
        rec = (
            db.query(models.EditPlanVersion)
            .filter(models.EditPlanVersion.project_id == project_id)
            .order_by(models.EditPlanVersion.version.desc())
            .first()
        )
        if rec is not None:
            return dict(rec.plan_json)
    finally:
        db.close()
    path = _project_file(project_id, "edit_plan.json")
    if path.exists():
        return _json.loads(path.read_text())
    return None


def _save_plan_version(project_id: str, plan: dict, created_by: str) -> int:
    """Persist a new EditPlanVersion + sync edit_plan.json. Returns version."""
    from . import models
    from .db import SessionLocal

    db = SessionLocal()
    try:
        latest = (
            db.query(models.EditPlanVersion)
            .filter(models.EditPlanVersion.project_id == project_id)
            .order_by(models.EditPlanVersion.version.desc())
            .first()
        )
        version = (latest.version + 1) if latest else 1
        db.add(models.EditPlanVersion(
            project_id=project_id, version=version,
            plan_json=plan, created_by=created_by,
        ))
        db.commit()
    finally:
        db.close()
    path = _project_file(project_id, "edit_plan.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json.dumps(plan, indent=2))
    return version


def _ensure_source_link(project_id: str) -> None:
    """Safety net: make sure storage/projects/<pid>/source.* exists for the
    analysis stage (Worker B scans that dir)."""
    import shutil as _shutil
    from pathlib import Path as _Path

    from . import models
    from .config import storage_root as _sr
    from .db import SessionLocal

    root = _sr()
    projdir = root / "projects" / project_id
    if any(projdir.glob("source.*")):
        return
    db = SessionLocal()
    try:
        project = db.get(models.Project, project_id)
        src_rel = project.source_path if project else None
    finally:
        db.close()
    if not src_rel:
        return
    src = root / src_rel
    if not src.exists():
        return
    projdir.mkdir(parents=True, exist_ok=True)
    link = projdir / f"source{src.suffix}"
    try:
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(src if src.is_absolute() else _Path(_os.path.relpath(src, projdir)))
    except Exception:
        try:
            _shutil.copy2(src, link)
        except Exception as e:
            logger.warning("source link failed for %s: %s", project_id, e)


def _run_analysis(project_id: str) -> None:
    """Lazy import of Worker B's analysis_pipeline."""
    from .services.analysis_pipeline import run_analysis as _impl  # noqa

    _ensure_source_link(project_id)

    def cb(pct, stage):  # Worker B calls cb(percent:int, stage:str)
        report_progress(project_id, str(stage), float(pct or 0), str(stage), kind="analyze")

    try:
        _impl(project_id, progress_cb=cb)
    except ImportError as e:
        msg = f"analysis_pipeline not available: {e}"
        logger.error(msg)
        _set_project_status(project_id, "error")
        report_progress(project_id, "error", 0, msg, kind="analyze")
        raise RuntimeError(msg) from e
    except Exception as e:
        logger.exception("analysis failed for %s", project_id)
        _set_project_status(project_id, "error")
        report_progress(project_id, "error", 0, f"Analysis failed: {e}", kind="analyze")
        raise
    _set_project_status(project_id, "ready")
    report_progress(project_id, "done", 100, "Analysis complete", kind="analyze")


def _run_plan(project_id: str, style_opts: dict | None = None) -> None:
    """Lazy import of Worker B's planner.build_edit_plan(analysis, style_opts, cb)."""
    from .services.planner import build_edit_plan as _impl  # noqa

    analysis = _load_analysis(project_id)  # FileNotFoundError -> error path below

    def cb(pct, stage):  # Worker B calls cb(percent, stage)
        report_progress(project_id, str(stage), float(pct or 0), str(stage), kind="plan")

    try:
        try:
            plan = _impl(analysis, style_opts or {}, progress_cb=cb)
        except TypeError:
            plan = _impl(analysis, style_opts or {})
    except ImportError as e:
        msg = f"planner not available: {e}"
        logger.error(msg)
        _set_project_status(project_id, "error")
        report_progress(project_id, "error", 0, msg, kind="plan")
        raise RuntimeError(msg) from e
    except Exception as e:
        logger.exception("planning failed for %s", project_id)
        _set_project_status(project_id, "error")
        report_progress(project_id, "error", 0, f"Planning failed: {e}", kind="plan")
        raise
    if not isinstance(plan, dict):
        raise RuntimeError(f"planner returned unexpected type {type(plan)}")
    version = _save_plan_version(project_id, plan, created_by="ai")
    logger.info("edit plan v%s saved for project %s", version, project_id)
    _set_project_status(project_id, "ready")
    report_progress(project_id, "done", 100, f"Edit plan ready (v{version})", kind="plan")


def _run_render(render_job_id: str, project_id: str | None = None) -> None:
    """Lazy import of Worker C's render_pipeline.run_render."""
    from .services.render_pipeline import run_render as _impl  # noqa

    from . import models
    from .config import storage_root as _sr
    from .db import SessionLocal

    db = SessionLocal()
    try:
        job = db.get(models.RenderJob, render_job_id)
        if job is None:
            raise RuntimeError(f"RenderJob {render_job_id} not found")
        pid = project_id or job.project_id
        preset = job.preset
        job.status = "running"
        job.progress = 0.0
        db.commit()
    finally:
        db.close()

    plan = _load_plan(pid)
    if plan is None:
        msg = "No edit plan — run POST /projects/{id}/plan first"
        _fail_render(render_job_id, pid, msg)
        raise RuntimeError(msg)

    _set_project_status(pid, "rendering")

    def cb(stage, pct, eta=None):  # Worker C calls cb(stage, pct, eta_seconds)
        message = str(stage)
        if isinstance(eta, (int, float)) and eta:
            message = f"{stage} — ETA {eta:.0f}s"
        report_progress(pid, str(stage), float(pct or 0), message,
                        kind="render", render_job_id=render_job_id)

    try:
        out_path = _impl(pid, preset, plan, cb)
    except ImportError as e:
        msg = f"render_pipeline not available: {e}"
        logger.error(msg)
        _fail_render(render_job_id, pid, msg)
        raise RuntimeError(msg) from e
    except Exception as e:
        logger.exception("render failed for job %s", render_job_id)
        _fail_render(render_job_id, pid, str(e))
        raise

    root = _sr()
    try:
        rel = _os.path.relpath(out_path, root)
    except Exception:
        rel = out_path
    db = SessionLocal()
    try:
        job = db.get(models.RenderJob, render_job_id)
        if job:
            job.status = "done"
            job.progress = 100.0
            job.output_path = rel
            db.commit()
    finally:
        db.close()
    _set_project_status(pid, "done")
    report_progress(pid, "done", 100, "Render complete", kind="render",
                    render_job_id=render_job_id)


def _fail_render(render_job_id: str, project_id: str, error: str) -> None:
    from . import models
    from .db import SessionLocal

    db = SessionLocal()
    try:
        job = db.get(models.RenderJob, render_job_id)
        if job:
            job.status = "error"
            job.error = error[:2000]
            # Refund the deducted credits — the user pays only for completed renders.
            if job.credits_charged:
                project = db.get(models.Project, project_id)
                if project:
                    user = db.get(models.User, project.user_id)
                    if user:
                        user.credits = round(user.credits + job.credits_charged, 2)
                        db.add(models.CreditTransaction(
                            user_id=user.id,
                            amount=job.credits_charged,
                            reason=f"render failed refund job={render_job_id}",
                        ))
            db.commit()
    finally:
        db.close()
    _set_project_status(project_id, "error")
    report_progress(project_id, "error", 0, f"Render failed: {error[:200]}", kind="render",
                    render_job_id=render_job_id)


# ------------------------------------------------------------------ celery
# Created at import time (after the 1s socket test) when Redis is reachable.
celery_app = None

if redis_available():
    try:
        from celery import Celery

        celery_app = Celery("cutpilot", broker=settings.redis_url, backend=settings.redis_url)
        celery_app.conf.task_track_started = True

        @celery_app.task(name="run_analysis_task")
        def run_analysis_task(project_id: str):
            _run_analysis(project_id)

        @celery_app.task(name="run_plan_task")
        def run_plan_task(project_id: str, style_opts: dict | None = None):
            _run_plan(project_id, style_opts or {})

        @celery_app.task(name="run_render_task")
        def run_render_task(render_job_id: str, project_id: str | None = None):
            _run_render(render_job_id, project_id)

        logger.info("Celery mode: Redis reachable, tasks registered")
    except Exception as e:
        logger.warning("Celery init failed (%s) — falling back to in-process executor", e)
        celery_app = None
else:
    logger.info("In-process mode: ThreadPoolExecutor fallback (no Redis)")


# ------------------------------------------------------- in-process pool
def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cutpilot")
        return _executor


def _run_inprocess(job_id: str, kind: str, project_id: str, payload: dict) -> None:
    _jobs[job_id]["status"] = "running"
    try:
        if kind == "analyze":
            _run_analysis(project_id)
        elif kind == "plan":
            _run_plan(project_id, payload.get("style_opts") or {})
        elif kind == "render":
            _run_render(payload["render_job_id"], project_id)
        else:
            raise ValueError(f"unknown job kind: {kind}")
        _jobs[job_id]["status"] = "done"
    except Exception as e:
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["error"] = str(e)[:500]


# ------------------------------------------------------------------ api
_TASK_BY_KIND = {"analyze": "run_analysis_task", "plan": "run_plan_task", "render": "run_render_task"}


def submit_job(kind: str, project_id: str, payload: dict | None = None) -> str:
    """Submit a pipeline job. Returns a job_id string.

    kind: "analyze" | "plan" | "render"
    payload: e.g. {"style_opts": {...}} for plan, {"render_job_id": ...} for render.
    """
    if kind not in _TASK_BY_KIND:
        raise ValueError(f"unknown job kind: {kind}")
    payload = payload or {}
    job_id = uuid.uuid4().hex

    if celery_app is not None and redis_available():
        task = celery_app.tasks[_TASK_BY_KIND[kind]]
        if kind == "analyze":
            args = [project_id]
        elif kind == "plan":
            args = [project_id, payload.get("style_opts") or {}]
        else:
            args = [payload["render_job_id"], project_id]
        task.apply_async(args=args, task_id=job_id)
        _jobs[job_id] = {"job_id": job_id, "mode": "celery", "kind": kind,
                         "project_id": project_id, "status": "submitted"}
        logger.info("celery job %s submitted kind=%s project=%s", job_id, kind, project_id)
    else:
        _jobs[job_id] = {"job_id": job_id, "mode": "in-process", "kind": kind,
                         "project_id": project_id, "status": "queued"}
        _get_executor().submit(_run_inprocess, job_id, kind, project_id, payload)
        logger.info("in-process job %s submitted kind=%s project=%s", job_id, kind, project_id)
    return job_id


def get_job_status(job_id: str) -> dict:
    info = dict(_jobs.get(job_id, {"job_id": job_id, "status": "unknown"}))
    if info.get("mode") == "celery" and celery_app is not None:
        try:
            from celery.result import AsyncResult

            r = AsyncResult(job_id, app=celery_app)
            info["celery_state"] = r.state
            if r.state == "FAILURE":
                info["status"] = "error"
                info["error"] = str(r.info)[:500] if r.info else "task failed"
            elif r.state == "SUCCESS":
                info["status"] = "done"
            elif r.state in ("STARTED", "RETRY"):
                info["status"] = "running"
        except Exception as e:
            info["celery_lookup_error"] = str(e)[:200]
    return info


def worker_mode() -> str:
    return "celery" if (celery_app is not None and redis_available()) else "in-process"
