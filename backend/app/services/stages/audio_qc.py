"""CutPilot AI — audio QC stage.

Single ffmpeg pass (asplit into astats / volumedetect / ebur128 branches)
plus a numpy scan of decoded PCM for clipping spans:

  - noise_floor_db  (approx. from astats RMS floor)
  - clipping flag + clipping_spans (PCM samples at |x| >= 0.999 in runs)
  - volume_consistent (momentary loudness std from ebur128 < 6 LU)
  - flags[] + needs_enhancement
"""

from __future__ import annotations

import re
import subprocess

import numpy as np

MAXV_RE = re.compile(r"max_volume:\s*(-?[\d.]+|-\s*inf)\s*dB")
EBUR_SUMMARY_RE = re.compile(r"I:\s*(-?[\d.]+)\s*LUFS")
MOM_RE = re.compile(r"M:\s*(-?[\d.]+)")


def _run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stderr


def _decode_pcm16(path: str, sr: int = 16000) -> np.ndarray:
    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", path,
         "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
        capture_output=True,
    )
    if r.returncode != 0:
        raise RuntimeError("ffmpeg decode failed")
    return np.frombuffer(r.stdout, dtype=np.float32)


def _clipping_spans(pcm: np.ndarray, sr: int = 16000,
                    min_run_sec: float = 0.005,
                    merge_gap_sec: float = 0.1) -> list[dict]:
    """Spans where the signal sits at digital full-scale (|x| >= 0.999)."""
    mask = np.abs(pcm) >= 0.999
    if not mask.any():
        return []
    idx = np.flatnonzero(mask)
    # split into runs
    breaks = np.flatnonzero(np.diff(idx) > 1)
    runs = np.split(idx, breaks + 1)
    min_n = int(min_run_sec * sr)
    spans = [(r[0] / sr, (r[-1] + 1) / sr) for r in runs if len(r) >= min_n]
    # merge close spans
    merged: list[list[float]] = []
    for s, e in spans:
        if merged and s - merged[-1][1] <= merge_gap_sec:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    return [{"start": round(float(s), 2), "end": round(float(e), 2)}
            for s, e in merged]


def _noise_floor_db(pcm: np.ndarray, sr: int = 16000) -> float | None:
    """True noise-floor estimate: mean RMS of the quietest 5% of 100ms windows."""
    n = int(0.1 * sr)
    if len(pcm) < n:
        return None
    count = len(pcm) // n
    frames = pcm[: count * n].reshape(count, n)
    rms = np.sqrt(np.mean(frames ** 2, axis=1)) + 1e-9
    quiet = np.sort(20 * np.log10(rms))[: max(1, count // 20)]
    return round(float(quiet.mean()), 1)


def check_audio_quality(audio_path: str) -> dict:
    log = _run([
        "ffmpeg", "-hide_banner", "-i", audio_path,
        "-filter_complex",
        "asplit=3[a][b][c];"
        "[a]astats=metadata=1[a1];"
        "[b]volumedetect[b1];"
        "[c]ebur128=peak=true:framelog=quiet[c1]",
        "-map", "[a1]", "-map", "[b1]", "-map", "[c1]",
        "-f", "null", "-",
    ])

    max_v = MAXV_RE.search(log)
    max_db = float(max_v.group(1)) if max_v and "inf" not in max_v.group(1) else -99.0

    pcm = _decode_pcm16(audio_path)
    noise_floor_db = _noise_floor_db(pcm)
    clipping_spans = _clipping_spans(pcm)
    clipping = bool(clipping_spans) or max_db >= -1.0

    mom = [float(m) for m in MOM_RE.findall(log)]
    volume_consistent = (max(mom) - min(mom) < 6.0) if len(mom) > 4 else True
    integ = EBUR_SUMMARY_RE.search(log)
    integrated_lufs = float(integ.group(1)) if integ else None

    flags: list[str] = []
    if clipping:
        flags.append("clipping")
    if noise_floor_db is not None and noise_floor_db > -45.0:
        flags.append("high_noise_floor")
    if not volume_consistent:
        flags.append("inconsistent_volume")
    if integrated_lufs is not None and integrated_lufs < -20.0:
        flags.append("too_quiet")

    return {
        "noise_floor_db": noise_floor_db,
        "integrated_lufs": integrated_lufs,
        "max_volume_db": round(max_db, 1),
        "clipping": clipping,
        "clipping_spans": clipping_spans,
        "volume_consistent": volume_consistent,
        "flags": flags,
        "needs_enhancement": bool(flags),
    }
