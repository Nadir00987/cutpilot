"""Analytics-ready metadata generation.

Pure function over analysis.json: title, description, hashtags and tags per
platform (youtube / tiktok / instagram), plus copy-paste YouTube chapters.
No network, no LLM — deterministic rules so output is stable and testable.
"""
from __future__ import annotations

import re

PLATFORM_LIMITS = {
    "youtube": {"title": 100, "hashtags": 15, "desc": 5000},
    "tiktok": {"title": 150, "hashtags": 8, "desc": 2200},
    "instagram": {"title": 125, "hashtags": 30, "desc": 2200},
}

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "is", "are", "was", "were", "be", "been", "this", "that",
    "it", "its", "as", "by", "from", "you", "your", "we", "our", "i", "my",
    "so", "just", "like", "get", "got", "going", "gonna", "really", "very",
    "um", "uh", "uhh", "umm", "yeah", "okay", "well", "now", "then", "there",
}


def _keywords(analysis: dict, n: int = 8) -> list[str]:
    kws = analysis.get("keywords") or []
    phrases = [k.get("phrase", "") for k in kws if k.get("phrase")]
    if not phrases:
        # fallback: most frequent non-stopwords in the transcript
        words = re.findall(r"[a-zA-Z]{4,}", " ".join(
            w.get("w", "") for w in analysis.get("words", [])).lower())
        freq: dict[str, int] = {}
        for w in words:
            if w not in _STOPWORDS:
                freq[w] = freq.get(w, 0) + 1
        phrases = [w for w, _ in sorted(freq.items(), key=lambda kv: -kv[1])]
    return phrases[:n]


def _fmt_ts(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    return f"{m}:{s:02d}"


def generate_metadata(analysis: dict, platform: str = "youtube") -> dict:
    """Build publish-ready metadata from an analysis dict."""
    platform = platform.lower()
    limits = PLATFORM_LIMITS.get(platform, PLATFORM_LIMITS["youtube"])
    kws = _keywords(analysis)

    title = analysis.get("suggested_title") or ""
    if not title and analysis.get("summary"):
        title = analysis["summary"].split(".")[0].strip()
    title = title[: limits["title"]]

    hashtags = ["#" + re.sub(r"\W+", "", k).lower() for k in kws]
    hashtags = [h for h in hashtags if len(h) > 2][: limits["hashtags"]]

    hook = analysis.get("hook") or {}
    desc_lines = [
        analysis.get("summary", ""),
        "",
        "In this video:" if analysis.get("segments") else "",
    ]
    chapters = []
    for seg in analysis.get("segments", [])[:12]:
        ts = _fmt_ts(seg.get("start", 0))
        label = (seg.get("text") or "")[:60]
        chapters.append({"timestamp": ts, "start_sec": seg.get("start", 0), "label": label})
        if platform == "youtube":
            desc_lines.append(f"{ts} {label}")
    if hook.get("text"):
        desc_lines += ["", f"Hook: {hook['text'][:140]}"]
    desc_lines += ["", " ".join(hashtags)]
    description = "\n".join(l for l in desc_lines if l is not None)[: limits["desc"]]

    return {
        "platform": platform,
        "title": title,
        "description": description.strip(),
        "hashtags": hashtags,
        "tags": kws,  # plain keyword tags for YouTube tag box
        "chapters": chapters,  # copy-paste ready for YouTube description
        "thumbnail_texts": analysis.get("thumbnail_texts", [])[:3],
    }
