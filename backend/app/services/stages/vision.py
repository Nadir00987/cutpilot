"""CutPilot AI — vision stage (pluggable).

Environment:
    VISION_API_URL  HTTP endpoint for vision descriptions
    VISION_API_KEY  Bearer key (optional)

The endpoint receives::

    POST {VISION_API_URL}
    {"image_b64": "<jpeg base64>", "prompt": "<str>"}

and is expected to return JSON ``{"description": "..."}`` (a bare string
is also accepted). When the endpoint is absent, callers MUST continue
audio-only and record a note — never fail the pipeline over vision.
"""

from __future__ import annotations

import base64
import os
import subprocess
import tempfile

import httpx


def vision_available() -> bool:
    return bool(os.environ.get("VISION_API_URL"))


def extract_frames(video_path: str, n: int = 8) -> list[str]:
    """Extract up to ``n`` evenly spaced JPEG frames from ``video_path``.

    Returns a list of temp file paths (caller may delete them).
    """
    duration = _probe_duration(video_path)
    if duration <= 0:
        return []
    tmpdir = tempfile.mkdtemp(prefix="cutpilot_frames_")
    out = []
    for i in range(n):
        t = duration * (i + 0.5) / n
        frame_path = os.path.join(tmpdir, f"frame_{i:02d}.jpg")
        r = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}",
             "-i", video_path, "-frames:v", "1", "-q:v", "4", frame_path],
            capture_output=True,
        )
        if r.returncode == 0 and os.path.exists(frame_path):
            out.append(frame_path)
    return out


def _probe_duration(video_path: str) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", video_path],
            capture_output=True, text=True,
        )
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def describe_frame(image_path: str, prompt: str | None = None) -> str | None:
    """Return a natural-language description of one frame, or None if the
    vision endpoint is not configured / errors."""
    if not vision_available():
        return None
    prompt = prompt or (
        "Describe this video frame in one sentence: what is visible "
        "(person talking, screen share, product demo, outdoor, text on screen, etc.)?"
    )
    try:
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode()
        url = os.environ["VISION_API_URL"]
        headers = {"Content-Type": "application/json"}
        if os.environ.get("VISION_API_KEY"):
            headers["Authorization"] = f"Bearer {os.environ['VISION_API_KEY']}"
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, headers=headers,
                               json={"image_b64": image_b64, "prompt": prompt})
        if resp.status_code >= 400:
            return None
        data = resp.json()
        if isinstance(data, dict):
            return data.get("description") or data.get("text")
        if isinstance(data, str):
            return data
        return None
    except Exception:
        return None
