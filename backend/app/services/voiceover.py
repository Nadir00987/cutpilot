"""AI voiceover / dubbing service.

Pluggable TTS: the provider is chosen via TTS_PROVIDER env var
("openai" | "elevenlabs" | "none"). When no provider is configured the
service returns a stub response — but through the REAL code path (script
validation, timing estimation, output-path planning) so wiring a provider
later is a one-env-var change.
"""
from __future__ import annotations

import os
import re
import uuid

# Rough speaking rate used for timing estimates (words per minute).
WPM = 150


def estimate_duration_sec(script: str) -> float:
    words = len(re.findall(r"[A-Za-z0-9']+", script))
    return round(words / WPM * 60.0, 2)


def _output_path(project_id: int) -> str:
    storage = os.environ.get("STORAGE_DIR", "./storage")
    d = os.path.join(storage, "renders", f"project_{project_id}")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"voiceover_{uuid.uuid4().hex[:8]}.mp3")


def synthesize(script: str, voice: str = "default", project_id: int = 0) -> dict:
    """Synthesize `script` to an audio file. Returns a result dict.

    Real providers call out to the TTS API; "none" returns the stub.
    """
    script = (script or "").strip()
    if not script:
        raise ValueError("script must not be empty")
    if len(script) > 5000:
        raise ValueError("script too long (max 5000 chars)")

    provider = os.environ.get("TTS_PROVIDER", "none").lower()
    out_path = _output_path(project_id)
    base = {
        "status": "ok",
        "provider": provider,
        "voice": voice,
        "chars": len(script),
        "estimated_duration_sec": estimate_duration_sec(script),
        "audio_path": out_path,
    }

    if provider in ("", "none"):
        # Stub: real code path, no audio bytes produced.
        base["status"] = "stub"
        base["note"] = (
            "TTS_PROVIDER is not configured; no audio was synthesized. "
            "Set TTS_PROVIDER=openai|elevenlabs and TTS_API_KEY to enable."
        )
        return base
    if provider == "openai":
        return _synthesize_openai(script, voice, out_path, base)
    if provider == "elevenlabs":
        return _synthesize_elevenlabs(script, voice, out_path, base)
    raise ValueError(f"unknown TTS_PROVIDER={provider!r}")


def _synthesize_openai(script: str, voice: str, out_path: str, base: dict) -> dict:
    import httpx  # lazy: only needed when the provider is actually used

    api_key = os.environ.get("TTS_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("TTS_API_KEY (or OPENAI_API_KEY) is required for TTS_PROVIDER=openai")
    resp = httpx.post(
        "https://api.openai.com/v1/audio/speech",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": "tts-1", "input": script, "voice": voice, "response_format": "mp3"},
        timeout=120,
    )
    resp.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(resp.content)
    base["bytes"] = len(resp.content)
    return base


def _synthesize_elevenlabs(script: str, voice: str, out_path: str, base: dict) -> dict:
    import httpx  # lazy

    api_key = os.environ.get("TTS_API_KEY")
    if not api_key:
        raise RuntimeError("TTS_API_KEY is required for TTS_PROVIDER=elevenlabs")
    voice_id = voice if len(voice) > 10 else "21m00Tcm4TlvDq8ikWAM"
    resp = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={"text": script, "model_id": "eleven_multilingual_v2"},
        timeout=120,
    )
    resp.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(resp.content)
    base["bytes"] = len(resp.content)
    return base
