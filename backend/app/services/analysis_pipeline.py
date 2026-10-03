"""CutPilot AI — Stage B: deep analysis orchestrator.

``run_analysis(project_id, progress_cb) -> dict``

Orchestrates all 10 analysis stages, writes
``storage/projects/<pid>/analysis.json`` and returns the analysis dict.

## analysis.json schema (v1)

{
  "version": "1",
  "project_id": "<pid>",
  "source": {"path", "duration", "width", "height", "fps", "codec",
             "audio_channels", "bitrate", "orientation"},
  "language": "en", "language_probability": 0.99,
  "words": [{"word", "start", "end", "confidence", "low_confidence", "speaker"}],
  "segments": [{"start", "end", "text", "energy"}],
  "fillers": [{"start", "end", "word", "type", "action", "reason"}],
  "silences": [{"start", "end", "duration", "action"}],
  "scenes": [{"start", "end", "description", "source"}],   # source: vision|audio-only
  "speakers": [{"id": "SPEAKER_1", "label": "Speaker 1"}],
  "diarization_heuristic": true,
  "energy_profile": [{"start", "end", "energy"}],
  "highlights": [{"start", "end", "energy", "reason"}],
  "hook": {"start", "end", "text", "reason"},
  "keywords": [{"phrase", "score", "start", "end"}],
  "audio_qc": {"noise_floor_db", "integrated_lufs", "max_volume_db",
               "clipping", "clipping_spans", "volume_consistent",
               "flags", "needs_enhancement"},
  "summary": "...", "suggested_title": "...", "thumbnail_texts": [3],
  "chapters": [{"start", "title"}],
  "metadata": {"title", "description", "hashtags", "tags": {"youtube":[], "tiktok":[], "instagram":[]}},
  "notes": ["..."]
}

Resilience: any single stage that raises is recorded in ``notes`` and the
pipeline continues (graceful failure per MASTER_PROMPT §7).

Worker A interface contract (lazy import, best effort): the backend is
expected to expose ONE of ``app.db`` / ``app.database`` / ``app.models``
with a callable named one of ``update_project_status`` / ``set_project_status``
/ ``update_status`` taking ``(project_id: str, status: str)``. If none is
importable, the JSON is still written and the miss is logged to ``notes``.

Source video resolution: ``storage/projects/<pid>/`` is scanned for the
first file matching source.* / input.* / upload.* / *.mp4|*.mov|*.webm|
*.mkv|*.m4a|*.mp3|*.wav.
"""

from __future__ import annotations

import glob
import importlib
import json
import logging
import os
import subprocess
import time

log = logging.getLogger("cutpilot.analysis")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
STORAGE = os.environ.get("CUTPILOT_STORAGE", os.path.join(REPO_ROOT, "storage"))
VERSION = "1"

MEDIA_EXTS = (".mp4", ".mov", ".webm", ".mkv", ".m4v",
              ".m4a", ".mp3", ".wav", ".aac", ".ogg")


def _project_dir(project_id: str) -> str:
    d = os.path.join(STORAGE, "projects", project_id)
    os.makedirs(d, exist_ok=True)
    return d


def _find_source_video(project_dir: str) -> str | None:
    for name in ("source.*", "input.*", "upload.*"):
        hits = sorted(glob.glob(os.path.join(project_dir, name)))
        if hits:
            return hits[0]
    for ext in MEDIA_EXTS:
        hits = sorted(glob.glob(os.path.join(project_dir, f"*{ext}")))
        if hits:
            return hits[0]
    return None


def _probe_source(path: str) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration,bit_rate:stream=width,height,avg_frame_rate,codec_name,channels",
         "-of", "json", path],
        capture_output=True, text=True,
    )
    data = json.loads(r.stdout or "{}")
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("width")), {})
    a = next((s for s in streams if s.get("channels")), {})
    width, height = int(v.get("width", 0)), int(v.get("height", 0))
    fps_raw = v.get("avg_frame_rate", "0/1")
    try:
        num, den = fps_raw.split("/")
        fps = round(float(num) / float(den), 2) if float(den) else 0.0
    except Exception:
        fps = 0.0
    orientation = "16:9"
    if width and height:
        ratio = width / height
        orientation = "9:16" if ratio < 0.8 else ("1:1" if ratio < 1.2 else "16:9")
    return {
        "path": path,
        "duration": round(float(fmt.get("duration", 0) or 0), 3),
        "width": width, "height": height, "fps": fps,
        "codec": v.get("codec_name", ""),
        "audio_channels": int(a.get("channels", 0)),
        "bitrate": int(fmt.get("bit_rate", 0) or 0),
        "orientation": orientation,
    }


def _update_project_status(project_id: str, status: str) -> bool:
    """Best-effort status update through Worker A's db layer (lazy import)."""
    for mod_name in ("app.db", "app.database", "app.models"):
        try:
            mod = importlib.import_module(mod_name)
        except Exception:
            continue
        for fn_name in ("update_project_status", "set_project_status", "update_status"):
            fn = getattr(mod, fn_name, None)
            if callable(fn):
                try:
                    fn(project_id, status)
                    return True
                except Exception as e:  # noqa: BLE001
                    log.warning("status update failed: %s", e)
                    return False
    return False


def run_analysis(project_id: str, progress_cb=None) -> dict:
    """Run all Stage-B analysis stages for ``project_id``.

    ``progress_cb`` is called as ``progress_cb(percent:int, stage:str)``.
    """
    from .stages import (
        transcribe_audio, detect_fillers, detect_silence, detect_scenes,
        diarize, assign_speakers_to_words, DIARIZATION_HEURISTIC_NOTE,
        compute_energy, detect_hook, extract_keywords,
        check_audio_quality, summarize,
    )

    t_all = time.time()
    notes: list[str] = []

    def progress(pct: int, stage: str):
        if progress_cb:
            try:
                progress_cb(pct, stage)
            except Exception:  # noqa: BLE001
                pass

    project_dir = _project_dir(project_id)
    source_path = _find_source_video(project_dir)
    if not source_path:
        raise FileNotFoundError(
            f"No source media found in {project_dir} "
            "(expected source.* / input.* / upload.* or a media file).")

    _update_project_status(project_id, "analyzing")

    # ---- stage 1: probe -------------------------------------------------
    progress(4, "probe")
    source = _probe_source(source_path)
    duration = source["duration"]
    has_audio = source["audio_channels"] > 0
    audio_only = not (source["width"] and source["height"])
    analysis: dict = {
        "version": VERSION, "project_id": project_id, "source": source,
        "language": "en", "language_probability": 0.0,
        "words": [], "segments": [], "fillers": [], "silences": [],
        "scenes": [], "speakers": [], "diarization_heuristic": True,
        "energy_profile": [], "highlights": [],
        "hook": {"start": 0.0, "end": 0.0, "text": "", "reason": ""},
        "keywords": [], "audio_qc": {},
        "summary": "", "suggested_title": "", "thumbnail_texts": [],
        "chapters": [], "metadata": {}, "notes": notes,
    }

    def stage(name: str, pct: int, fn):
        t0 = time.time()
        try:
            result = fn()
            progress(pct, name)
            log.info("stage %s done in %.1fs", name, time.time() - t0)
            return result
        except Exception as e:  # noqa: BLE001 - resilient: never abort
            msg = f"Stage '{name}' failed: {type(e).__name__}: {e}"
            log.warning(msg)
            notes.append(msg)
            progress(pct, name)
            return None

    # ---- stage 2: transcription ----------------------------------------
    progress(8, "transcription")
    tx = stage("transcription", 28, lambda: transcribe_audio(source_path))
    if tx:
        analysis["language"] = tx["language"]
        analysis["language_probability"] = tx["language_probability"]
        analysis["words"] = tx["words"]
        analysis["segments"] = tx["segments"]
        if tx["dropped_hallucinations"]:
            notes.append(f"Dropped {tx['dropped_hallucinations']} hallucinated "
                         "word(s) on near-silent spans (< -40 dBFS).")
    else:
        notes.append("Transcription failed — manual script paste can be used; "
                     "continuing with audio-only structural analysis.")

    # ---- stage 3: fillers + silence -------------------------------------
    def _filler_silence():
        out = {}
        if analysis["words"]:
            out["fillers"] = detect_fillers(analysis["words"])
        if has_audio:
            out["silences"] = detect_silence(source_path)
        return out
    fs = stage("fillers+silence", 40, _filler_silence)
    if fs:
        analysis["fillers"] = fs.get("fillers", [])
        analysis["silences"] = fs.get("silences", [])

    # ---- stage 4: scenes + vision ---------------------------------------
    def _scenes():
        if audio_only:
            return [{"start": 0.0, "end": duration,
                     "description": "audio-only analysis (vision unavailable)",
                     "source": "audio-only"}]
        sc = detect_scenes(source_path, duration)
        if not any(s["source"] == "vision" for s in sc):
            notes.append("Vision endpoint unavailable — scene descriptions "
                         "are audio-only.")
        return sc
    sc = stage("scenes+vision", 52, _scenes)
    if sc:
        analysis["scenes"] = sc

    # ---- stage 5: diarization --------------------------------------------
    def _diar():
        spans = diarize(source_path) if has_audio else [(0.0, duration, "SPEAKER_1")]
        assign_speakers_to_words(analysis["words"], spans)
        return spans
    spans = stage("diarization", 62, _diar)
    if spans:
        seen = []
        for _, _, sp in spans:
            if sp not in seen:
                seen.append(sp)
        analysis["speakers"] = [
            {"id": sp, "label": f"Speaker {i + 1}"} for i, sp in enumerate(seen)]
        notes.append(DIARIZATION_HEURISTIC_NOTE)

    # ---- stage 6: energy + hook -------------------------------------------
    def _energy():
        return compute_energy(source_path, analysis["words"], duration)
    en = stage("energy", 72, _energy)
    if en:
        analysis["energy_profile"] = en["profile"]
        analysis["highlights"] = en["highlights"]
        for seg, prof in zip(analysis["segments"], en["profile"]):
            seg["energy"] = prof["energy"]

    def _keywords():
        return extract_keywords(analysis["words"])
    kw = stage("keywords", 78, _keywords)
    if kw:
        analysis["keywords"] = kw

    def _hook():
        return detect_hook(analysis["words"], analysis["energy_profile"],
                           analysis["keywords"], duration)
    hk = stage("hook", 82, _hook)
    if hk:
        analysis["hook"] = hk

    # ---- stage 7: audio QC -------------------------------------------------
    aq = stage("audio_qc", 88, lambda: check_audio_quality(source_path))
    if aq:
        analysis["audio_qc"] = aq

    # ---- stage 8: summary / metadata / chapters -----------------------------
    summ = stage("summary", 94, lambda: summarize(
        analysis["words"], analysis["segments"], analysis["keywords"],
        analysis["scenes"], duration))
    if summ:
        for k in ("summary", "suggested_title", "thumbnail_texts",
                  "metadata", "chapters"):
            analysis[k] = summ[k]
        analysis["metadata"]["title"] = summ["suggested_title"]

    # ---- stage 9: write json + status ----------------------------------------
    progress(97, "finalize")
    out_path = os.path.join(project_dir, "analysis.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)
    _update_project_status(project_id, "ready")
    progress(100, "done")
    notes.append(f"Analysis completed in {time.time() - t_all:.1f}s "
                 f"({len(analysis['words'])} words).")
    return analysis
