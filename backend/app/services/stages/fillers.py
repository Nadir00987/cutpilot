"""CutPilot AI — filler & mistake detection stage.

Detects:
  - filler words: um, uh, uhh, erm, ah, er
  - repeated words (w == next word)
  - false starts (fragment < 3 chars followed by a restart of the word)
  - long pauses (> 1.2 s gap between words)

Each hit gets a suggested action ("cut" / "keep") and a reason. Nothing is
hard-deleted here — the planner decides.
"""

from __future__ import annotations

import re

FILLER_RE = re.compile(r"^(um+|uh+|erm+|ah+|er+|hmm+)$", re.IGNORECASE)
LONG_PAUSE_SEC = 1.2


def _clean(w: str) -> str:
    return re.sub(r"[^\w']", "", w or "").lower()


def detect_fillers(words: list[dict]) -> list[dict]:
    hits: list[dict] = []
    for i, w in enumerate(words):
        cw = _clean(w["word"])
        if not cw:
            continue

        # 1. filler words -> cut
        if FILLER_RE.match(cw):
            hits.append({
                "start": w["start"], "end": w["end"], "word": w["word"],
                "type": "filler", "action": "cut",
                "reason": f"Filler word '{cw}' — removing tightens pacing.",
            })
            continue

        nxt = words[i + 1] if i + 1 < len(words) else None

        # 2. repeated words -> cut the duplicate
        if nxt and _clean(nxt["word"]) == cw:
            hits.append({
                "start": nxt["start"], "end": nxt["end"], "word": nxt["word"],
                "type": "repeat", "action": "cut",
                "reason": f"Repeated word '{cw}' — keeping first occurrence.",
            })

        # 3. false starts: tiny fragment followed by a word that starts with it
        if nxt and len(cw) < 3:
            ncw = _clean(nxt["word"])
            if ncw.startswith(cw) and len(ncw) > len(cw):
                hits.append({
                    "start": w["start"], "end": w["end"], "word": w["word"],
                    "type": "false_start", "action": "cut",
                    "reason": f"False start '{cw}' before '{ncw}' — cut the fragment.",
                })

        # 4. long pause between words -> keep (silence stage removes these)
        if nxt:
            gap = nxt["start"] - w["end"]
            if gap > LONG_PAUSE_SEC:
                hits.append({
                    "start": w["end"], "end": nxt["start"], "word": "",
                    "type": "long_pause", "action": "keep",
                    "reason": f"{gap:.1f}s pause kept here; removed via silence detection.",
                })
    return hits
