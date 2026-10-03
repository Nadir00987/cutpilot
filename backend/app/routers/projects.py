"""Project CRUD + upload ingest + URL import + source/analysis/thumbnail serving."""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import auth as auth_lib
from .. import models
from ..config import storage_root
from ..db import get_db
from ..services.ingest import ALLOWED_EXTS, ingest_upload

logger = logging.getLogger("cutpilot.routers.projects")

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str = "Untitled project"


class ProjectUpdate(BaseModel):
    name: str | None = None


class ImportUrlIn(BaseModel):
    url: str


def _get_owned(db: Session, project_id: str, user: models.User) -> models.Project:
    project = db.get(models.Project, project_id)
    if project is None or (project.user_id != user.id and user.role != "admin"):
        raise HTTPException(404, "Project not found")
    return project


def _project_out(p: models.Project) -> dict:
    return {
        "id": p.id,
        "user_id": p.user_id,
        "name": p.name,
        "status": p.status,
        "orientation": p.orientation,
        "duration": p.duration,
        "source_path": p.source_path,
        "thumbnail_path": p.thumbnail_path,
        "style_opts": p.style_opts,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


@router.get("")
def list_projects(
    q: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    query = db.query(models.Project).filter(models.Project.user_id == user.id)
    if status:
        query = query.filter(models.Project.status == status)
    if q:
        query = query.filter(models.Project.name.ilike(f"%{q}%"))
    total = query.count()
    items = query.order_by(models.Project.created_at.desc()).offset(offset).limit(limit).all()
    return {"total": total, "items": [_project_out(p) for p in items]}


@router.post("", status_code=201)
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    project = models.Project(user_id=user.id, name=body.name.strip() or "Untitled project")
    db.add(project)
    db.commit()
    db.refresh(project)
    return _project_out(project)


@router.get("/{project_id}")
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    return _project_out(_get_owned(db, project_id, user))


@router.patch("/{project_id}")
def update_project(
    project_id: str,
    body: ProjectUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    project = _get_owned(db, project_id, user)
    if body.name is not None:
        project.name = body.name.strip() or project.name
    db.commit()
    return _project_out(project)


@router.delete("/{project_id}")
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    project = _get_owned(db, project_id, user)
    db.delete(project)
    db.commit()
    # Best-effort storage cleanup (never fail the API on this).
    root = storage_root()
    for sub in ("uploads", "projects", "renders", "thumbnails"):
        shutil.rmtree(root / sub / project_id, ignore_errors=True)
    return {"detail": "Project deleted"}


# ------------------------------------------------------------------ upload
@router.post("/{project_id}/upload")
def upload_source(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    from ..services.ingest import detect_orientation

    project = _get_owned(db, project_id, user)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(400, f"Unsupported file type {ext!r}. Allowed: {sorted(ALLOWED_EXTS)}")

    project.status = "uploading"
    db.commit()

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    try:
        shutil.copyfileobj(file.file, tmp)
        tmp.close()
        asset, meta = ingest_upload(project_id, tmp.name, file.filename or f"source{ext}")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.exception("ingest failed for %s", project_id)
        project.status = "error"
        db.commit()
        raise HTTPException(500, f"Ingest failed: {e}")
    finally:
        Path(tmp.name).unlink(missing_ok=True)

    project.duration = meta.get("duration")
    project.orientation = detect_orientation(meta.get("width"), meta.get("height"))
    project.source_path = asset.path
    project.thumbnail_path = meta.get("thumbnail_strip")
    project.status = "ready"
    db.commit()
    return {"project": _project_out(project), "metadata": meta}


# --------------------------------------------------------------- url import
@router.post("/{project_id}/import-url")
def import_url(
    project_id: str,
    body: ImportUrlIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    from ..services.ingest import detect_orientation

    project = _get_owned(db, project_id, user)
    root = storage_root()
    updir = root / "uploads" / project_id
    updir.mkdir(parents=True, exist_ok=True)
    out_tmpl = str(updir / "source.%(ext)s")

    project.status = "uploading"
    db.commit()
    try:
        subprocess.run(
            ["yt-dlp", "--no-playlist", "-f", "mp4/best", "-o", out_tmpl, body.url],
            capture_output=True, text=True, timeout=900, check=True,
        )
    except subprocess.TimeoutExpired:
        project.status = "error"
        db.commit()
        raise HTTPException(504, "Download timed out")
    except subprocess.CalledProcessError as e:
        project.status = "error"
        db.commit()
        tail = (e.stderr or "")[-600:]
        raise HTTPException(400, f"Could not download URL: {tail}")

    downloaded = sorted(updir.glob("source.*"))
    if not downloaded:
        project.status = "error"
        db.commit()
        raise HTTPException(500, "Download produced no file")
    src = downloaded[0]

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=src.suffix)
    tmp.close()
    shutil.move(str(src), tmp.name)
    try:
        asset, meta = ingest_upload(project_id, tmp.name, f"import{src.suffix}")
    except Exception as e:
        logger.exception("ingest failed for %s", project_id)
        project.status = "error"
        db.commit()
        raise HTTPException(500, f"Ingest failed: {e}")
    finally:
        Path(tmp.name).unlink(missing_ok=True)

    project.duration = meta.get("duration")
    project.orientation = detect_orientation(meta.get("width"), meta.get("height"))
    project.source_path = asset.path
    project.thumbnail_path = meta.get("thumbnail_strip")
    project.status = "ready"
    db.commit()
    return {"project": _project_out(project), "metadata": meta}


# ------------------------------------------------------------------ files
@router.get("/{project_id}/source")
def get_source(
    project_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    project = _get_owned(db, project_id, user)
    if not project.source_path:
        raise HTTPException(404, "No source media yet")
    path = storage_root() / project.source_path
    if not path.exists():
        raise HTTPException(404, "Source file missing from storage")
    return FileResponse(path, media_type="video/mp4", filename=f"{project.name}-source{path.suffix}")


@router.get("/{project_id}/analysis")
def get_analysis(
    project_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    import json

    _get_owned(db, project_id, user)
    path = storage_root() / "projects" / project_id / "analysis.json"
    if not path.exists():
        raise HTTPException(404, "Analysis not ready yet")
    return json.loads(path.read_text())


@router.get("/{project_id}/thumbnail")
def get_thumbnail(
    project_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    project = _get_owned(db, project_id, user)
    if not project.thumbnail_path:
        raise HTTPException(404, "No thumbnail yet")
    path = storage_root() / project.thumbnail_path
    if not path.exists():
        raise HTTPException(404, "Thumbnail missing from storage")
    return FileResponse(path, media_type="image/png")
