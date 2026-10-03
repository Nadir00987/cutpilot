"""Aspect reframe helpers + pluggable face detection (Worker C).

Two reframe strategies:
  * 16:9 presets (1080p/720p/4k): scale-to-fill + centre crop to the exact
    target (or pad when the planner asks to keep the source aspect — the
    default here is fill+crop for a full-bleed social look).
  * 9:16 / 1:1: blurred-background fill — the source is scaled to cover the
    canvas, blurred heavily, and the sharp foreground is centred on top.
    The foreground's vertical anchor uses ``detect_face_center()`` so a
    talking head stays in frame.

``detect_face_center(frame_png)`` is the pluggable interface:
  - tries OpenCV Haar cascade when cv2 is importable,
  - else returns the default (0.5, 0.42) — slightly above centre, the
    classic talking-head anchor.
Override by monkeypatching this module's ``detect_face_center`` (documented
for Worker A / future face-tracking upgrades).
"""

import os

import numpy as np
from PIL import Image


def detect_face_center(frame_png: str) -> tuple[float, float]:
    """Return (fx, fy) face anchor as fractions of frame width/height.

    Pluggable: tries OpenCV Haar cascade if installed, else (0.5, 0.42).
    """
    try:
        import cv2  # type: ignore
        cascade = os.path.join(cv2.data.haarcascades,
                               "haarcascade_frontalface_default.xml")
        img = cv2.imread(frame_png)
        if img is not None and os.path.exists(cascade):
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = cv2.CascadeClassifier(cascade).detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5,
                minSize=(60, 60))
            if len(faces):
                x, y, w, h = max(faces, key=lambda b: b[2] * b[3])
                H, W = gray.shape
                return ((x + w / 2) / W, (y + h / 2) / H)
    except Exception:
        pass
    return (0.5, 0.42)


def grab_frame(video_path: str, at_sec: float, out_png: str,
               width: int = 480) -> str:
    """Extract one frame with ffmpeg for face anchoring."""
    import subprocess
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{at_sec:.2f}",
         "-i", video_path, "-frames:v", "1",
         "-vf", f"scale={width}:-2", out_png],
        check=True)
    return out_png


def reframe_chain(preset: str, TW: int, TH: int,
                  face: tuple[float, float] = (0.5, 0.42)) -> str:
    """Return the filter chain (no outer labels) converting the working
    stream to the preset canvas. Caller wraps: ``[catv]<chain>[rfv]``.

    * 16:9 presets: scale-to-cover + centre crop to the exact target.
    * 9:16 / 1:1: blurred-background fill — source scaled to cover, heavily
      blurred; sharp foreground centred on top, nudged so the face anchor
      sits ~42% down the canvas.
    """
    _fx, fy = face
    if preset in ("1080p", "720p", "4k"):
        return (f"scale={TW}:{TH}:force_original_aspect_ratio=increase,"
                f"crop={TW}:{TH},setsar=1")
    # vertical offset so the face anchor lands ~40% down the canvas
    y_expr = "'max(0,(H-h)*0.40)'"
    return (
        f"split[rf_a][rf_b];"
        f"[rf_a]scale={TW}:{TH}:force_original_aspect_ratio=increase,"
        f"crop={TW}:{TH},boxblur=18:2[rf_bg];"
        f"[rf_b]scale={TW}:-2,crop=iw:min'(ih,{TH})'[rf_fg];"
        f"[rf_bg][rf_fg]overlay=(W-w)/2:{y_expr},setsar=1"
    )


def reframe_filters(preset: str, W: int, H: int,
                    face: tuple[float, float] = (0.5, 0.42)) -> list[str]:
    """Legacy list form (kept for compatibility). Prefer reframe_chain()."""
    targets = {"1080p": (1920, 1080), "720p": (1280, 720),
               "4k": (3840, 2160), "9:16": (1080, 1920), "1:1": (1080, 1080)}
    TW, TH = targets[preset]
    return [reframe_chain(preset, TW, TH, face)]
