"""CutPilot AI — content summary stage.

Produces:
  - summary: 3-5 sentences (extractive: top keyword sentences; LLM if configured)
  - suggested_title
  - thumbnail_texts[3]: short punchy phrases for thumbnails
  - metadata: {description, hashtags[], tags{platform:[...]}}
  - chapters: [{start, title}] from scenes / energy segments

Rules-first; LLM (if configured) may refine copy.
"""

from __future__ import annotations

import json
import re

from .llm import chat, LLMNotConfigured


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if len(p.split()) >= 4]


def summarize(words: list[dict], segments: list[dict], keywords: list[dict],
              scenes: list[dict], duration: float) -> dict:
    full_text = " ".join(s["text"] for s in segments).strip()
    sentences = _sentences(full_text)

    # extractive: score sentences by keyword hits
    kw_phrases = [(k["phrase"].lower(), k["score"]) for k in keywords]
    scored = []
    for s in sentences:
        sl = s.lower()
        score = sum(sc for ph, sc in kw_phrases if ph in sl)
        scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    picked: list[str] = []
    for _, s in scored:
        if len(picked) >= 5:
            break
        if s not in picked:
            picked.append(s)
    if len(picked) < 3 and sentences:
        for s in sentences:
            if s not in picked:
                picked.append(s)
            if len(picked) >= 3:
                break
    summary = " ".join(picked[:5]) if picked else full_text[:400]

    title = _suggested_title(keywords, picked)
    thumbs = _thumbnail_texts(keywords, picked)

    summary, title, thumbs = _maybe_llm_refine(summary, title, thumbs)

    metadata = _metadata(summary, keywords)
    chapters = _chapters(scenes, words, duration)

    return {
        "summary": summary,
        "suggested_title": title,
        "thumbnail_texts": thumbs,
        "metadata": metadata,
        "chapters": chapters,
    }


def _suggested_title(keywords: list[dict], sentences: list[str]) -> str:
    if keywords:
        top = " ".join(k["phrase"] for k in keywords[:3]).title()
        return f"{top} — Explained"
    if sentences:
        return sentences[0][:70]
    return "Untitled Video"


def _thumbnail_texts(keywords: list[dict], sentences: list[str]) -> list[str]:
    out: list[str] = []
    for k in keywords[:3]:
        phrase = k["phrase"].title()
        if len(phrase.split()) <= 4:
            out.append(phrase.upper())
    for s in sentences:
        toks = s.split()
        if 2 <= len(toks) <= 5 and len(out) < 3 and s not in out:
            out.append(s.rstrip(".!?").upper())
    while len(out) < 3:
        out.append("WATCH THIS")
    return out[:3]


def _metadata(summary: str, keywords: list[dict]) -> dict:
    tags = [re.sub(r"\W+", "", k["phrase"].lower()) for k in keywords[:10]]
    hashtags = [f"#{t}" for t in tags if len(t) > 2][:8]
    desc = summary[:2000]
    return {
        "title": "",
        "description": f"{desc}\n\n{' '.join(hashtags)}",
        "hashtags": hashtags,
        "tags": {
            "youtube": tags[:8],
            "tiktok": tags[:5],
            "instagram": tags[:8],
        },
    }


def _chapters(scenes: list[dict], words: list[dict], duration: float) -> list[dict]:
    chapters: list[dict] = []
    if len(scenes) >= 2:
        for sc in scenes:
            ws = [w["word"] for w in words
                  if sc["start"] <= w["start"] < sc["end"]][:5]
            title = " ".join(ws).strip(" ,.") or "Scene"
            chapters.append({"start": sc["start"], "title": title[:40].title()})
    else:
        # fall back to 4 even chunks
        n = 4
        for i in range(n):
            t = duration * i / n
            ws = [w["word"] for w in words
                  if t <= w["start"] < t + duration / n][:5]
            chapters.append({"start": round(t, 2),
                             "title": (" ".join(ws).strip(" ,.") or f"Part {i+1}")[:40].title()})
    return chapters


def _maybe_llm_refine(summary: str, title: str, thumbs: list[str]):
    try:
        out = chat([
            {"role": "system",
             "content": "You write YouTube titles, summaries and thumbnail text. "
                        "Reply with JSON {\"summary\": ..., \"title\": ..., "
                        "\"thumbnail_texts\": [3 short punchy strings]}."},
            {"role": "user",
             "content": f"SUMMARY: {summary}\nTITLE: {title}\nTHUMBS: {thumbs}"},
        ], json_mode=True)
        data = json.loads(out)
        return (data.get("summary", summary), data.get("title", title),
                data.get("thumbnail_texts", thumbs)[:3] or thumbs)
    except (LLMNotConfigured, Exception):
        return summary, title, thumbs
