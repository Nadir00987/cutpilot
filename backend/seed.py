#!/usr/bin/env python3
"""CutPilot AI seed script. Run from backend/ with the project venv:

    backend/.venv/bin/python seed.py

Idempotent: re-running never duplicates users/projects.
Creates:
  - admin@cutpilot.ai / AdminPass123!  (admin, 100 credits)
  - demo@cutpilot.ai  / DemoPass123!   (user, 50 credits)
  - a demo project owned by the demo user.
If backend/seed_data/demo_analysis.json exists (Worker E), it and
demo_edit_plan.json are copied into storage/projects/demo/; otherwise the
script builds real demo media with ffmpeg and runs the real analysis +
planner via lazy imports (skipped gracefully if those services are missing).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from app import models  # noqa: E402
from app.auth import hash_password  # noqa: E402
from app.config import storage_root  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402

ADMIN_EMAIL, ADMIN_PASS = "admin@cutpilot.ai", "AdminPass123!"
DEMO_EMAIL, DEMO_PASS = "demo@cutpilot.ai", "DemoPass123!"


def get_or_create_user(db, email, password, name, role, credits):
    user = db.query(models.User).filter(models.User.email == email).first()
    if user:
        print(f"user exists: {email}")
        return user
    user = models.User(
        email=email, password_hash=hash_password(password),
        name=name, role=role, credits=credits,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    print(f"created user: {email} (role={role}, credits={credits})")
    return user


def build_demo_media(demo_project_id: str) -> Path:
    """Generate a 60s talking-head-style test clip with ffmpeg (real media)."""
    out = Path(tempfile.gettempdir()) / "cutpilot_demo_source.mp4"
    if out.exists() and out.stat().st_size > 0:
        return out
    print("generating demo media with ffmpeg (60s testsrc2 + tone)...")
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=60",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=60",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
            "-c:a", "aac", "-shortest", str(out),
        ],
        check=True,
    )
    return out


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        admin = get_or_create_user(db, ADMIN_EMAIL, ADMIN_PASS, "CutPilot Admin", "admin", 100.0)
        demo = get_or_create_user(db, DEMO_EMAIL, DEMO_PASS, "Demo Creator", "user", 50.0)

        project = db.get(models.Project, "demo")
        if project is None:
            project = models.Project(
                id="demo", user_id=demo.id, name="Demo project — sample edit",
                status="uploading",
            )
            db.add(project)
            db.commit()
            print("created demo project (id=demo)")
        else:
            print("demo project exists")

        pdir = storage_root() / "projects" / "demo"
        pdir.mkdir(parents=True, exist_ok=True)

        seed_analysis = HERE / "seed_data" / "demo_analysis.json"
        seed_plan = HERE / "seed_data" / "demo_edit_plan.json"
        if seed_analysis.exists():
            # Curated demo data wins (real pipeline output, committed to seed_data).
            shutil.copy(seed_analysis, pdir / "analysis.json")
            print("copied seed_data/demo_analysis.json")
            seed_media = HERE / "seed_data" / "demo_source.mp4"
            if seed_media.exists():
                shutil.copy(seed_media, pdir / "source.mp4")
                project.source_path = str(pdir / "source.mp4")
                project.duration = 35.7
                project.orientation = "16:9"
                print("copied seed_data/demo_source.mp4 (demo preview media)")
            if seed_plan.exists():
                shutil.copy(seed_plan, pdir / "edit_plan.json")
                existing_v1 = db.query(models.EditPlanVersion).filter(
                    models.EditPlanVersion.project_id == "demo",
                    models.EditPlanVersion.version == 1,
                ).first()
                if not existing_v1:
                    db.add(models.EditPlanVersion(
                        project_id="demo", version=1,
                        plan_json=json.loads(seed_plan.read_text()),
                        created_by="seed",
                    ))
                    db.commit()
                print("copied seed_data/demo_edit_plan.json (plan v1)")
            project.status = "ready"
            db.commit()
            return

        # No curated seed data: build real media + run the real pipeline.
        if not project.source_path:
            from app.services.ingest import detect_orientation, ingest_upload

            src = build_demo_media("demo")
            tmp = Path(tempfile.gettempdir()) / "demo_ingest.mp4"
            shutil.copy(src, tmp)
            asset, meta = ingest_upload("demo", tmp, "demo.mp4")
            project.duration = meta.get("duration")
            project.orientation = detect_orientation(meta.get("width"), meta.get("height"))
            project.source_path = asset.path
            project.thumbnail_path = meta.get("thumbnail_strip")
            project.status = "ready"
            db.commit()
            print(f"demo media ingested: duration={project.duration:.1f}s orientation={project.orientation}")

        # Real analysis (Worker B) — lazy, skip gracefully if missing.
        if not (pdir / "analysis.json").exists():
            try:
                from app.services.analysis_pipeline import run_analysis

                print("running real analysis on demo media...")
                run_analysis("demo", progress_cb=lambda s, p, m: print(f"  [{s}] {p:.0f}% {m}"))
                project.status = "ready"
                db.commit()
            except ImportError as e:
                print(f"analysis_pipeline not available yet, skipping ({e})")

        if (pdir / "analysis.json").exists() and not (pdir / "edit_plan.json").exists():
            try:
                from app.services.planner import build_edit_plan

                print("building real edit plan on demo media...")
                try:
                    build_edit_plan("demo", {}, progress_cb=lambda s, p, m: print(f"  [{s}] {p:.0f}% {m}"))
                except TypeError:
                    try:
                        build_edit_plan("demo", {})
                    except TypeError:
                        build_edit_plan("demo")
                print("demo edit plan built")
            except ImportError as e:
                print(f"planner not available yet, skipping ({e})")

        print("seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
