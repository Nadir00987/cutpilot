"""CutPilot AI — transcription stage (faster-whisper).

Environment:
    WHISPER_MODEL  tiny (default) | base | small | ...

Runs on CPU with int8 compute. Produces word-level timestamps with
per-word confidence, language detection, and filters hallucinated words
that fall on near-silent spans (mean level < -40 dBFS).
"""

from __future__ import annotations

import math
import os
import subprocess
import tempfile

import numpy as np

def _sanitize_proxy_env() -> None:
    """This VM's no_proxy may contain IPv6 literals ([::1]) which crash httpx
    proxy parsing inside huggingface_hub during model download. Strip
    bracketed entries; leave the rest untouched."""
    for key in ("no_proxy", "NO_PROXY"):
        val = os.environ.get(key)
        if val:
            os.environ[key] = ",".join(
                p for p in val.split(",") if p and "[" not in p)


_sanitize_proxy_env()


def _decode_pcm16(path: str, sr: int = 16000) -> np.ndarray:
    """Decode any audio to mono float32 PCM at ``sr`` via ffmpeg."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", path,
           "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg decode failed: {r.stderr[:200].decode(errors='ignore')}")
    return np.frombuffer(r.stdout, dtype=np.float32)


def transcribe_audio(audio_path: str) -> dict:
    """Transcribe ``audio_path``.

    Returns:
        {
          "language": str, "language_probability": float,
          "words": [{"word", "start", "end", "confidence", "low_confidence", "speaker"}],
          "segments": [{"start", "end", "text", "energy"}],
          "dropped_hallucinations": int,
        }
    ``speaker`` is left empty here; analysis_pipeline fills it after diarization.
    """
    from faster_whisper import WhisperModel

    model_name = os.environ.get("WHISPER_MODEL", "tiny")
    model = WhisperModel(model_name, device="cpu", compute_type="int8")

    segments_iter, info = model.transcribe(
        audio_path,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )

    pcm = _decode_pcm16(audio_path)
    sr = 16000
    dropped = 0
    words: list[dict] = []
    segments: list[dict] = []

    for seg in segments_iter:
        if not seg.words:
            continue
        seg_words: list[dict] = []
        for w in seg.words:
            conf = float(w.probability or 0.0)
            # Hallucination filter: mean dBFS of the word span.
            s0, s1 = int(w.start * sr), max(int(w.end * sr), int(w.start * sr) + 1)
            span = pcm[s0:s1] if s0 < len(pcm) else np.array([], dtype=np.float32)
            if span.size:
                rms = float(np.sqrt(np.mean(span ** 2)))
                db = 20 * math.log10(rms + 1e-9)
            else:
                db = -999.0
            if db < -40.0:
                dropped += 1
                continue
            item = {
                "word": w.word.strip(),
                "start": round(float(w.start), 3),
                "end": round(float(w.end), 3),
                "confidence": round(conf, 3),
                "low_confidence": conf < 0.5,
                "speaker": "",
            }
            words.append(item)
            seg_words.append(item)
        if seg_words:
            segments.append({
                "start": seg_words[0]["start"],
                "end": seg_words[-1]["end"],
                "text": seg.text.strip(),
                "energy": 0.0,  # filled by the energy stage
            })

    return {
        "language": info.language,
        "language_probability": round(float(info.language_probability or 0.0), 3),
        "words": words,
        "segments": segments,
        "dropped_hallucinations": dropped,
    }
