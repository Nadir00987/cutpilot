"""Auto chapter generation (Worker C).

``get_chapters(analysis)`` -> (text, chapters) where text is copy-paste
YouTube chapter text ("00:00 Intro\\n02:15 Topic ...") and chapters is a
list of {"time": sec, "label": str}.

Prefers analysis["segments"] (Worker B: {start,end,topic|title,energy});
falls back to chunking the transcript into ~60s blocks titled by their
first few words. Times are EDITED-timeline seconds — the caller (timeline
UI / export page) is responsible for mapping if needed; chapters are
computed from the kept-span transcript so they already reflect the edit.
"""

from .common import fmt_clock


def _from_segments(analysis: dict) -> list[dict] | None:
    segs = analysis.get("segments")
    if not segs:
        return None
    out = []
    for s in segs:
        label = (s.get("topic") or s.get("title") or s.get("label")
                 or "Chapter").strip()
        out.append({"time": float(s.get("start", 0)), "label": label})
    return out or None


def _from_words(analysis: dict, block: float = 60.0) -> list[dict]:
    words = analysis.get("words") or []
    if not words:
        return [{"time": 0.0, "label": "Intro"}]
    chapters, cur_start, cur_words = [], 0.0, []
    for w in words:
        if w["start"] - cur_start >= block and cur_words:
            title = " ".join(x["word"] for x in cur_words[:6]).strip(" ,.")
            chapters.append({"time": cur_start, "label": title.title() or "Part"})
            cur_start = w["start"]
            cur_words = []
        cur_words.append(w)
    if cur_words:
        title = " ".join(x["word"] for x in cur_words[:6]).strip(" ,.")
        chapters.append({"time": cur_start, "label": title.title() or "Part"})
    if chapters and chapters[0]["time"] > 1.0:
        chapters.insert(0, {"time": 0.0, "label": "Intro"})
    elif chapters:
        chapters[0]["label"] = "Intro"
    return chapters


def get_chapters(analysis: dict) -> tuple[str, list[dict]]:
    """Return (copy_paste_text, chapter_list)."""
    chapters = _from_segments(analysis) or _from_words(analysis)
    chapters.sort(key=lambda c: c["time"])
    # de-dupe near-identical timestamps
    dedup = []
    for c in chapters:
        if not dedup or c["time"] - dedup[-1]["time"] >= 2.0:
            dedup.append(c)
    text = "\n".join(f"{fmt_clock(c['time'])} {c['label']}" for c in dedup)
    return text, dedup
