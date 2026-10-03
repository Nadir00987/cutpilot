"""CutPilot AI backend — FastAPI app factory / entrypoint."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import jobs, models  # noqa: F401  (models registers tables + extras hook)
from .config import settings, storage_root
from .db import Base, engine
from .routers import admin, auth, billing, brandkit, pipeline, projects, render, templates
from .ws import router as ws_router

logger = logging.getLogger("cutpilot")

# Extension hook: Worker E may provide app/routers/extras.py. Absence is fine.
try:
    from .routers import extras as extras_router  # type: ignore

    _has_extras = True
except ImportError:
    extras_router = None
    _has_extras = False

# Extension hook: Worker E may provide app/models_extras.py. Absence is fine.
try:
    import app.models_extras  # noqa: F401  (also imported via models.py)
except ImportError:
    pass


def create_app() -> FastAPI:
    app = FastAPI(title="CutPilot AI", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(projects.router, prefix="/api/v1")
    app.include_router(pipeline.router, prefix="/api/v1")
    app.include_router(render.router, prefix="/api/v1")
    app.include_router(billing.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")
    app.include_router(brandkit.router, prefix="/api/v1")
    app.include_router(templates.router, prefix="/api/v1")
    app.include_router(ws_router, prefix="/api/v1")
    if _has_extras and extras_router is not None:
        app.include_router(extras_router.router, prefix="/api/v1")
        logger.info("extras router registered")
    else:
        logger.warning("app.routers.extras not present — skipping (Worker E provides it)")

    @app.get("/api/v1/healthz", tags=["meta"])
    def healthz():
        return {"status": "ok", "app": settings.app_name}

    # Ensure storage tree exists BEFORE mounting it (StaticFiles requires it).
    root = storage_root()
    for sub in (
        "uploads", "projects", "renders", "thumbnails",
        "assets/broll", "assets/music", "brandkit",
    ):
        (root / sub).mkdir(parents=True, exist_ok=True)

    # Serve renders / thumbnails / brandkit files.
    app.mount("/storage", StaticFiles(directory=str(root)), name="storage")

    @app.on_event("startup")
    def _startup():
        if settings.jwt_secret == "dev-only-insecure-secret-change-me":
            logger.warning("JWT_SECRET is the dev default — set a real secret in production!")
        Base.metadata.create_all(bind=engine)
        logger.info(
            "CutPilot AI up. worker_mode=%s redis=%s db=%s",
            jobs.worker_mode(),
            settings.redis_url,
            settings.database_url.split("@")[-1],
        )

    return app


app = create_app()
