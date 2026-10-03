"""Style templates: GET /templates reads backend/data/templates/*.json
(written by Worker E; empty list if none). Applying a template merges its
"style" block into the latest edit plan -> new version."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import auth as auth_lib
from .. import models
from ..config import BACKEND_ROOT
from ..db import get_db

logger = logging.getLogger("cutpilot.routers.templates")

router = APIRouter(tags=["templates"])


class ApplyTemplateIn(BaseModel):
    template_id: str


def _load_templates() -> list[dict]:
    tdir = BACKEND_ROOT / "data" / "templates"
    templates = []
    if not tdir.exists():
        return templates
    for path in sorted(tdir.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            data.setdefault("id", path.stem)
            templates.append(data)
        except Exception as e:
            logger.warning("bad template %s: %s", path, e)
    return templates


@router.get("/templates")
def list_templates():
    return {"templates": _load_templates()}


@router.post("/projects/{project_id}/apply-template")
def apply_template(
    project_id: str,
    body: ApplyTemplateIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_lib.get_current_user),
):
    from .pipeline import _get_owned, _latest_plan, _save_plan_version

    project = _get_owned(db, project_id, user)
    template = next((t for t in _load_templates() if t.get("id") == body.template_id), None)
    if template is None:
        raise HTTPException(404, f"Template {body.template_id!r} not found")

    latest = _latest_plan(db, project_id)
    if latest is None:
        raise HTTPException(400, "Generate an edit plan first (POST /projects/{id}/plan)")

    plan = json.loads(json.dumps(latest.plan_json))  # deep copy
    style = dict(plan.get("style") or {})
    style.update(template.get("style") or {})
    plan["style"] = style
    plan.setdefault("applied_template", template["id"])

    rec = _save_plan_version(db, project, plan, created_by=f"template:{template['id']}")
    return {
        "version": rec.version,
        "template": template["id"],
        "plan": rec.plan_json,
    }
