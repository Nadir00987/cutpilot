"""CutPilot AI — energy scoring stage.

Per 2 s window: energy 0-100 from normalized RMS loudness blended with
speech rate (words/sec). High-energy windows (> 75) are highlight
candidates used by hook detection, shorts extraction and emoji reactions.
"""

from __future__ import annotations

import subprocess

import numpy as np


def _decode_pcm16(path: str, sr: int = 16000) -> np.ndarray:
    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", path,
         "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
        capture_output=True,
    )
    if r.returncode != 0:
        raise RuntimeError("ffmpeg decode failed")
    return np.frombuffer(r.stdout, dtype=np.float32)


def compute_energy(audio_path: str, words: list[dict],
                   duration: float, win_sec: float = 2.0) -> dict:
    """Returns {"profile": [{start,end,energy}], "highlights": [{start,end,energy,reason}]}."""
    pcm = _decode_pcm16(audio_path)
    sr = 16000
    n = int(win_sec * sr)
    count = max(1, int(duration / win_sec))
    frames = []
    for i in range(count):
        s0, s1 = i * n, min((i + 1) * n, len(pcm))
        seg = pcm[s0:s1]
        frames.append(float(np.sqrt(np.mean(seg ** 2))) if seg.size else 0.0)
    arr = np.array(frames)
    loud = (arr - arr.min()) / (arr.max() - arr.min() + 1e-9)

    # speech rate per window
    starts = np.array([w["start"] for w in words]) if words else np.array([])
    profile = []
    for i in range(count):
        ws, we = i * win_sec, (i + 1) * win_sec
        nwords = int(((starts >= ws) & (starts < we)).sum()) if starts.size else 0
        rate = nwords / win_sec  # words per second
        rate_norm = min(1.0, rate / 3.0)  # ~3 wps = lively speech
        energy = round(float(100 * (0.65 * loud[i] + 0.35 * rate_norm)), 1)
        profile.append({"start": round(ws, 2), "end": round(we, 2),
                        "energy": energy})

    highlights = [
        {**p, "reason": f"High energy ({p['energy']}) — loudness + speech rate spike."}
        for p in profile if p["energy"] >= 75
    ]
    return {"profile": profile, "highlights": highlights}
