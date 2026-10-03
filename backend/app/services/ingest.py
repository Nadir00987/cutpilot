"""Upload ingest: ffprobe, orientation detection, thumbnail strip, waveform.

Storage contract (shared with all workers):
    storage/uploads/<pid>/source.<ext>
    storage/projects/<pid>/{analysis.json, edit_plan.json}
    storage/renders/<pid>/*.mp4
    storage/thumbnails/<pid>/*.png
    storage/assets/{broll,music}/
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from ..config import storage_root

logger = logging.getLogger("cutpilot.ingest")

ALLOWED_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".mp3", ".wav"}


def _run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=True)


# ------------------------------------------------------------------- probe
def probe(path: str | Path) -> dict:
    """ffprobe a media file -> metadata dict."""
    path = str(path)
    out = _run([
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_streams", "-show_format", path,
    ])
    data = json.loads(out.stdout)
    streams = data.get("streams", [])
    fmt = data.get("format", {})
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)

    width = int(v["width"]) if v and v.get("width") else None
    height = int(v["height"]) if v and v.get("height") else None
    fps = 0.0
    if v and v.get("avg_frame_rate"):
        try:
            num, den = v["avg_frame_rate"].split("/")
            fps = float(num) / float(den) if float(den) else 0.0
        except Exception:
            fps = 0.0

    return {
        "duration": float(fmt.get("duration") or 0.0),
        "width": width,
        "height": height,
        "fps": round(fps, 3),
        "codec": (v or {}).get("codec_name"),
        "audio_codec": (a or {}).get("codec_name"),
        "audio_channels": int(a["channels"]) if a and a.get("channels") else 0,
        "bitrate": int(fmt.get("bit_rate") or 0),
        "has_audio": a is not None,
        "has_video": v is not None,
        "format": fmt.get("format_name"),
    }


def detect_orientation(w: int | None, h: int | None) -> str:
    """-> "16:9" | "9:16" | "1:1". Audio-only / unknown defaults to 16:9."""
    if not w or not h:
        return "16:9"
    if h > w * 1.05:
        return "9:16"
    if abs(w - h) <= max(w, h) * 0.05:
        return "1:1"
    return "16:9"


# ------------------------------------------------------------- derivatives
def make_thumbnail_strip(path: str | Path, out: str | Path, n: int = 8) -> Path:
    """Tile n evenly-spaced frames into one PNG strip."""
    info = probe(path)
    fps = info["fps"] or 30.0
    total = max(1, int(info["duration"] * fps))
    step = max(1, total // n)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-v", "error", "-i", str(path),
        "-vf", f"select='not(mod(n\\,{step}))',scale=320:-1,tile={n}x1",
        "-frames:v", "1", str(out),
    ])
    return out


def make_waveform(path: str | Path, out_png: str | Path) -> Path:
    """Render an audio waveform PNG (showwavespic). Raises if no audio."""
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-v", "error", "-i", str(path),
        "-filter_complex", "showwavespic=s=1200x240:colors=0x38bdf8",
        "-frames:v", "1", str(out_png),
    ])
    return out_png


# ------------------------------------------------------------------ ingest
def ingest_upload(project_id: str, src_path: str | Path, filename: str):
    """Move an uploaded file into storage/uploads/<pid>/source.<ext>,
    probe it, build thumbnail strip + waveform, create the Asset row.

    Returns (asset_row, metadata_dict).
    """
    from .. import models
    from ..db import SessionLocal

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise ValueError(f"Unsupported file type {ext!r}. Allowed: {sorted(ALLOWED_EXTS)}")

    root = storage_root()
    updir = root / "uploads" / project_id
    thumbdir = root / "thumbnails" / project_id
    updir.mkdir(parents=True, exist_ok=True)
    thumbdir.mkdir(parents=True, exist_ok=True)

    dest = updir / f"source{ext}"
    if Path(src_path).resolve() != dest.resolve():
        shutil.move(str(src_path), str(dest))

    # Worker B's analysis_pipeline looks for source.* inside
    # storage/projects/<pid>/ — link it there (same file, no duplication).
    projdir = root / "projects" / project_id
    projdir.mkdir(parents=True, exist_ok=True)
    link = projdir / f"source{ext}"
    try:
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(dest)
    except Exception:
        try:
            shutil.copy2(dest, link)
        except Exception as e:
            logger.warning("could not link source into projects dir: %s", e)

    meta = probe(dest)
    meta["audio_only"] = not meta["has_video"]
    meta["original_filename"] = filename
    orientation = detect_orientation(meta["width"], meta["height"])

    strip_path = thumbdir / "strip.png"
    wave_path = thumbdir / "waveform.png"
    try:
        make_thumbnail_strip(dest, strip_path)
        meta["thumbnail_strip"] = str(strip_path.relative_to(root))
    except Exception as e:
        logger.warning("thumbnail strip failed for %s: %s", project_id, e)
    if meta["has_audio"]:
        try:
            make_waveform(dest, wave_path)
            meta["waveform"] = str(wave_path.relative_to(root))
        except Exception as e:
            logger.warning("waveform failed for %s: %s", project_id, e)

    db = SessionLocal()
    try:
        asset = models.Asset(
            project_id=project_id, kind="source", path=str(dest.relative_to(root)), meta=meta
        )
        db.add(asset)
        db.commit()
        db.refresh(asset)
        return asset, meta
    finally:
        db.close()
