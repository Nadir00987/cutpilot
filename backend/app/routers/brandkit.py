"""Brand kit: per-user JSON (logo path, colors, fonts, intro/outro, watermark)
stored as files under storage/brandkit/<user_id>/ — no extra tables needed."""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import auth as auth_lib
from .. import models
from ..config import storage_root

logger = logging.getLogger("cutpilot.routers.brandkit")

router = APIRouter(prefix="/brand-kit", tags=["brand-kit"])

DEFAULT_KIT = {
    "logo_path": None,
    "colors": {"primary": "#38bdf8", "secondary": "#a78bfa", "background": "#0b0f1a"},
    "fonts": {"heading": "Inter", "body": "Inter"},
    "intro": {"enabled": False, "duration_sec": 2.5, "template": "fade"},
    "outro": {"enabled": False, "duration_sec": 3.0, "template": "endcard"},
    "watermark": {"enabled": False, "opacity": 0.5, "position": "bottom-right"},
}


class BrandKitIn(BaseModel):
    colors: dict | None = None
    fonts: dict | None = None
    intro: dict | None = None
    outro: dict | None = None
    watermark: dict | None = None


def _kit_dir(user_id: int) -> Path:
    d = storage_root() / "brandkit" / str(user_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_kit(user_id: int) -> dict:
    path = _kit_dir(user_id) / "brandkit.json"
    kit = dict(DEFAULT_KIT)
    if path.exists():
        try:
            kit.update(json.loads(path.read_text()))
        except Exception as e:
            logger.warning("brandkit json corrupt for user %s: %s", user_id, e)
    return kit


def _write_kit(user_id: int, kit: dict) -> None:
    (_kit_dir(user_id) / "brandkit.json").write_text(json.dumps(kit, indent=2))


@router.get("")
def get_brand_kit(user: models.User = Depends(auth_lib.get_current_user)):
    return _read_kit(user.id)


@router.put("")
def update_brand_kit(
    body: BrandKitIn, user: models.User = Depends(auth_lib.get_current_user)
):
    kit = _read_kit(user.id)
    for field in ("colors", "fonts", "intro", "outro", "watermark"):
        val = getattr(body, field)
        if val is not None:
            merged = dict(kit.get(field) or {})
            merged.update(val)
            kit[field] = merged
    _write_kit(user.id, kit)
    return kit


@router.post("/logo")
def upload_logo(
    file: UploadFile = File(...),
    user: models.User = Depends(auth_lib.get_current_user),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".svg"):
        raise HTTPException(400, "Logo must be png/jpg/webp/svg")
    dest = _kit_dir(user.id) / f"logo{ext}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    kit = _read_kit(user.id)
    kit["logo_path"] = f"brandkit/{user.id}/logo{ext}"
    _write_kit(user.id, kit)
    return {"logo_path": kit["logo_path"]}


@router.get("/logo")
def get_logo(user: models.User = Depends(auth_lib.get_current_user)):
    kit = _read_kit(user.id)
    if not kit.get("logo_path"):
        raise HTTPException(404, "No logo uploaded")
    path = storage_root() / kit["logo_path"]
    if not path.exists():
        raise HTTPException(404, "Logo file missing from storage")
    return FileResponse(path)
