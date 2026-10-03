"""CutPilot AI — hook detection stage.

Picks the strongest 3-5 s hook candidate: the window inside the first 30%
of the video with the best ``energy_density * keyword_score``. If an LLM is
configured it may rewrite the hook text; otherwise a rules-based pick is
returned with a reason.
"""

from __future__ import annotations

import json

from .llm import chat, LLMNotConfigured

HOOK_WORDS = {
    "secret", "free", "never", "always", "mistake", "how", "why", "best",
    "worst", "stop", "start", "new", "easy", "fast", "million", "shocking",
    "amazing", "ultimate", "proven", "ai", "money", "grow", "viral",
}


def detect_hook(words: list[dict], energy_profile: list[dict],
                keywords: list[dict], duration: float) -> dict:
    if not words:
        return {"start": 0.0, "end": 0.0, "text": "",
                "reason": "No words transcribed — hook unavailable."}

    search_end = duration * 0.30
    candidates = []
    for win_len in (3.0, 4.0, 5.0):
        t = 0.0
        while t + win_len <= search_end + 0.01:
            wspan = [w for w in words if w["start"] >= t and w["end"] <= t + win_len]
            if len(wspan) >= 5:
                e = _mean_energy(t, t + win_len, energy_profile)
                ks = _keyword_score(wspan, keywords)
                text = " ".join(w["word"] for w in wspan)
                candidates.append({
                    "start": round(t, 3), "end": round(t + win_len, 3),
                    "text": text,
                    "score": e * (1.0 + ks),
                    "energy": e, "keyword_score": ks,
                })
            t += 0.5
    if not candidates:
        first = words[0]
        return {"start": first["start"],
                "end": min(first["start"] + 4.0, duration),
                "text": " ".join(w["word"] for w in words[:15]),
                "reason": "Fallback: first 15 words used as hook."}

    best = max(candidates, key=lambda c: c["score"])
    text = _maybe_llm_rewrite(best["text"])
    return {
        "start": best["start"], "end": best["end"], "text": text,
        "reason": (f"Highest energy_density ({best['energy']:.1f}) × "
                   f"keyword_score ({best['keyword_score']:.2f}) within first "
                   f"30% of the video; hooks the viewer early."),
    }


def _mean_energy(t0: float, t1: float, profile: list[dict]) -> float:
    vals = [p["energy"] for p in profile
            if p["end"] > t0 and p["start"] < t1]
    return sum(vals) / len(vals) / 100.0 if vals else 0.3


def _keyword_score(wspan: list[dict], keywords: list[dict]) -> float:
    kset = {k["phrase"].lower() for k in keywords}
    text = " ".join(w["word"] for w in wspan).lower()
    score = sum(k["score"] for k in keywords
                if k["phrase"].lower() in text)
    hook_bonus = sum(1 for w in HOOK_WORDS if w in text)
    return score + 0.5 * hook_bonus


def _maybe_llm_rewrite(text: str) -> str:
    try:
        out = chat([
            {"role": "system",
             "content": "Rewrite this spoken hook into a punchy 3-5 second "
                        "video hook caption. Keep the meaning, max 15 words. "
                        "Reply with JSON {\"text\": \"...\"}."},
            {"role": "user", "content": text},
        ], json_mode=True)
        return json.loads(out).get("text", text)
    except (LLMNotConfigured, Exception):
        return text
