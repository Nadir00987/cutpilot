"""CutPilot AI — silence detection stage.

Uses ffmpeg ``silencedetect``. Threshold from ``SILENCE_THRESHOLD_SEC``
(default 0.8 s), noise floor -30 dB.
"""

from __future__ import annotations

import os
import re
import subprocess

START_RE = re.compile(r"silence_start:\s*([\d.]+)")
END_RE = re.compile(r"silence_end:\s*([\d.]+)")


def detect_silence(audio_path: str) -> list[dict]:
    threshold = float(os.environ.get("SILENCE_THRESHOLD_SEC", "0.8"))
    cmd = [
        "ffmpeg", "-hide_banner", "-i", audio_path,
        "-af", f"silencedetect=noise=-30dB:d={threshold}",
        "-f", "null", "-",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    log = r.stderr

    silences: list[dict] = []
    starts = START_RE.findall(log)
    ends = END_RE.findall(log)
    for s, e in zip(starts, ends):
        start, end = float(s), float(e)
        silences.append({
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(end - start, 3),
            "action": "cut",
        })
    return silences
