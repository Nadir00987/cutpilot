"""CutPilot AI — HEURISTIC speaker diarization (no librosa, no torch).

Per 0.5 s window of decoded mono PCM we compute RMS energy and spectral
centroid via numpy FFT. Speaker change points are detected where the
combined energy+centroid shift exceeds an adaptive threshold; the two
resulting clusters are labeled SPEAKER_1 / SPEAKER_2 by mean centroid.

This is a HEURISTIC — it separates turn-taking voices reasonably on clean
talking-head audio but is NOT true neural diarization. A neural diarizer
(e.g. pyannote) can replace ``diarize()`` behind the same interface.

Interface: ``diarize(audio_path) -> [(start, end, speaker), ...]``
"""

from __future__ import annotations

import subprocess

import numpy as np

HEURISTIC_NOTE = (
    "Speaker labels are HEURISTIC (energy + spectral-centroid turn detection, "
    "no neural diarization model). Reliable for clean 1-2 speaker talking-head "
    "audio; may mislabel overlapping speech or background noise."
)


def _decode_pcm16(path: str, sr: int = 16000) -> np.ndarray:
    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", path,
         "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
        capture_output=True,
    )
    if r.returncode != 0:
        raise RuntimeError("ffmpeg decode failed")
    return np.frombuffer(r.stdout, dtype=np.float32)


def _window_features(pcm: np.ndarray, sr: int, win_sec: float = 0.5):
    n = int(win_sec * sr)
    if n <= 0 or len(pcm) < n:
        return np.array([]), np.array([])
    count = len(pcm) // n
    frames = pcm[: count * n].reshape(count, n)
    energy = np.sqrt(np.mean(frames ** 2, axis=1)) + 1e-9
    mags = np.abs(np.fft.rfft(frames, axis=1))
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    centroid = (mags * freqs).sum(axis=1) / (mags.sum(axis=1) + 1e-9)
    return energy, centroid


def diarize(audio_path: str) -> list[tuple[float, float, str]]:
    pcm = _decode_pcm16(audio_path)
    sr = 16000
    win = 0.5
    energy, centroid = _window_features(pcm, sr, win)
    if energy.size < 4:
        dur = len(pcm) / sr
        return [(0.0, round(dur, 3), "SPEAKER_1")]

    # normalized shift signal
    e_norm = (energy - energy.min()) / (energy.max() - energy.min() + 1e-9)
    c_norm = (centroid - centroid.min()) / (centroid.max() - centroid.min() + 1e-9)
    shift = np.abs(np.diff(e_norm)) + 0.6 * np.abs(np.diff(c_norm))
    # ignore changes in near-silence
    shift = shift * (e_norm[:-1] > 0.08)
    thresh = shift.mean() + 2.2 * shift.std()
    change_idx = np.where(shift > thresh)[0] + 1
    # merge change points closer than 2 windows
    merged = []
    for i in change_idx:
        if not merged or i - merged[-1] >= 4:
            merged.append(i)

    bounds = [0] + merged + [len(e_norm)]
    # cluster window-centroids into 2 speakers
    win_speaker = np.zeros(len(e_norm), dtype=int)
    if merged:
        cvals = c_norm
        split = np.median(cvals)
        win_speaker = (cvals > split).astype(int)

    spans: list[tuple[float, float, str]] = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        if b <= a:
            continue
        seg = win_speaker[a:b]
        spk = int(np.round(seg.mean())) if seg.size else 0
        spans.append((round(a * win, 3), round(b * win, 3),
                      f"SPEAKER_{spk + 1}"))
    # merge adjacent same-speaker spans
    out: list[tuple[float, float, str]] = []
    for s, e, sp in spans:
        if out and out[-1][2] == sp and s - out[-1][1] <= win * 1.5:
            out[-1] = (out[-1][0], e, sp)
        else:
            out.append((s, e, sp))
    return out


def assign_speakers_to_words(words: list[dict],
                             spans: list[tuple[float, float, str]]) -> None:
    """Mutate ``words`` in place, setting each word's speaker from the
    diarization spans (by word midpoint)."""
    if not spans:
        for w in words:
            w["speaker"] = "SPEAKER_1"
        return
    for w in words:
        mid = (w["start"] + w["end"]) / 2
        label = spans[-1][2]
        for s, e, sp in spans:
            if s <= mid <= e:
                label = sp
                break
        w["speaker"] = label
