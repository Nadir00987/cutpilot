"""CutPilot AI — scene-cut detection stage.

ffmpeg ``select='gt(scene,0.35)'`` + ``showinfo`` yields scene-start times.
Descriptions come from ``vision.describe_frame``; when vision is unavailable
the description falls back to "audio-only analysis (vision unavailable)".
"""

from __future__ import annotations

import re
import subprocess

from .vision import describe_frame, extract_frames

PTS_RE = re.compile(r"pts_time:([\d.]+)")


def detect_scenes(video_path: str, duration: float) -> list[dict]:
    """Return scenes [{start, end, description, source}] where
    ``source`` is "vision" or "audio-only"."""
    cmd = [
        "ffmpeg", "-hide_banner", "-i", video_path,
        "-vf", "select='gt(scene,0.35)',showinfo",
        "-f", "null", "-",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    cuts = sorted({float(m) for m in PTS_RE.findall(r.stderr)})
    # drop the t=0 frame if present; build spans
    bounds = [0.0] + [c for c in cuts if c > 0.05] + [duration]

    frames = extract_frames(video_path, n=min(8, max(1, len(bounds) - 1)))
    scenes = []
    for i in range(len(bounds) - 1):
        start, end = round(bounds[i], 3), round(bounds[i + 1], 3)
        desc = describe_frame(frames[i]) if i < len(frames) else None
        if desc:
            source = "vision"
        else:
            desc = "audio-only analysis (vision unavailable)"
            source = "audio-only"
        scenes.append({"start": start, "end": end,
                       "description": desc, "source": source})
    for f in frames:  # best-effort cleanup
        try:
            import os
            os.remove(f)
        except OSError:
            pass
    return scenes
