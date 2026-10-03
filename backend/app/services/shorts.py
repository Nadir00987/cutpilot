"""Shorts extractor (Worker C).

``shorts_candidates(analysis, plan)`` -> 3 x {start, end, title, reason}:
top energy+keyword windows of 30-60s on the EDITED timeline.

``extract_shorts(project_id, progress_cb)`` renders the 3 candidates as
vertical 9:16 clips with captions burned in into
storage/renders/<pid>/short_{1,2,3}.mp4, reusing run_render with a clipped
sub-plan per candidate (cuts/graphics/captions restricted to the window,
intro+outro disabled).
"""

import copy
import json
import os

from .common import project_dir
from .render_pipeline import _TimeMap, _norm_cuts, run_render

LENGTHS = (30, 45, 60)
STEP = 10.0


def _edited_words(analysis: dict, plan: dict):
    """Words mapped to edited time via plan cuts."""
    words = analysis.get("words") or (plan.get("captions") or {}).get("words") or []
    spans = _norm_cuts(plan.get("cuts") or [])
    if not spans:
        return [], 0.0
    tmap = _TimeMap(spans)
    out = []
    for w in words:
        s, e = float(w["start"]), float(w["end"])
        if tmap.span_of((s + e) / 2) is None:
            continue
        out.append({"word": w["word"], "start": tmap(s), "end": tmap(e),
                    "emphasis": bool(w.get("emphasis"))})
    return out, tmap.edited


def _score_window(words, a, b, keywords):
    in_w = [w for w in words if a <= w["start"] < b]
    if not in_w:
        return 0.0, []
    dur = b - a
    wps = len(in_w) / dur
    hits = [w["word"] for w in in_w
            if w["word"].lower().strip(".,!?") in keywords or w.get("emphasis")]
    seen, uniq = set(), []
    for h in hits:
        hl = h.lower()
        if hl not in seen:
            seen.add(hl)
            uniq.append(h)
    return wps * 10 + len(uniq) * 6 + sum(1 for w in in_w if w.get("emphasis")) * 2, uniq[:4]


def shorts_candidates(analysis: dict, plan: dict) -> list[dict]:
    """Pick 3 non-overlapping 30-60s windows (edited time)."""
    words, edited_dur = _edited_words(analysis, plan)
    if edited_dur < 30:
        return []
    keywords = set(
        (k.get("phrase", "") if isinstance(k, dict) else str(k)).lower()
        for k in (analysis.get("keywords") or [])
    )
    cands = []
    for L in LENGTHS:
        t = 0.0
        while t + L <= edited_dur + 0.5:
            b = min(t + L, edited_dur)
            if b - t >= 25:
                score, hits = _score_window(words, t, b, keywords)
                cands.append((score, t, b, hits))
            t += STEP
    cands.sort(reverse=True, key=lambda c: c[0])
    picked = []
    for score, t, b, hits in cands:
        if all(b <= p["start"] + 2 or t >= p["end"] - 2 for p in picked):
            in_w = [w["word"] for w in words if t <= w["start"] < b][:7]
            picked.append({
                "start": round(t, 2), "end": round(b, 2),
                "title": " ".join(in_w).strip(" ,.")[:60] or "Highlight",
                "reason": (f"speech density + keywords: {', '.join(hits)}"
                           if hits else "high speech density window"),
                "score": round(score, 1),
            })
        if len(picked) == 3:
            break
    return picked


# ------------------------------------------------------------ extraction ---
def _load_project(project_id: str):
    pd = project_dir(project_id)
    with open(os.path.join(pd, "edit_plan.json")) as f:
        plan = json.load(f)
    analysis = {}
    ap = os.path.join(pd, "analysis.json")
    if os.path.exists(ap):
        with open(ap) as f:
            analysis = json.load(f)
    return plan, analysis


def _clip_plan_to_window(plan: dict, c: dict) -> dict:
    """Build a sub-plan covering edited window [c.start, c.end]."""
    spans = _norm_cuts(plan.get("cuts") or [])
    # edited ranges per span
    acc, pieces = 0.0, []
    for s, e in spans:
        es, ee = acc, acc + (e - s)
        o0, o1 = max(c["start"], es), min(c["end"], ee)
        if o1 - o0 > 0.2:
            pieces.append((s + (o0 - es), s + (o1 - es)))
        acc = ee

    sub = copy.deepcopy(plan)
    sub["cuts"] = [{"start": s, "end": e} for s, e in pieces]
    sub["source_duration"] = plan.get("source_duration")
    sub["intro_outro"] = {"intro": {"enabled": False},
                          "outro": {"enabled": False}}
    sub["title"] = c["title"]

    def overlaps(s, e):
        return any(s < pe and e > ps for ps, pe in pieces)

    def clip(s, e):
        for ps, pe in pieces:
            if s < pe and e > ps:
                return max(s, ps), min(e, pe)
        return None

    gfx = []
    for g in plan.get("graphics") or []:
        s, e = float(g.get("start", 0)), float(g.get("end", 0))
        rng = clip(s, e)
        if rng:
            g2 = dict(g)
            g2["start"], g2["end"] = rng
            gfx.append(g2)
    sub["graphics"] = gfx

    words = []
    for w in (plan.get("captions") or {}).get("words") or []:
        mid = (float(w["start"]) + float(w["end"])) / 2
        if any(ps <= mid <= pe for ps, pe in pieces):
            words.append(w)
    sub["captions"] = dict(plan.get("captions") or {}, words=words)

    br = []
    for b in plan.get("broll") or []:
        s, e = float(b.get("start", 0)), float(b.get("end", 0))
        rng = clip(s, e)
        if rng:
            b2 = dict(b)
            b2["start"], b2["end"] = rng
            br.append(b2)
    sub["broll"] = br
    return sub


def extract_shorts(project_id: str, progress_cb) -> list[str]:
    """Render the 3 candidate shorts (9:16, captions on). Returns paths."""
    plan, analysis = _load_project(project_id)
    cands = shorts_candidates(analysis, plan)
    paths = []
    for i, c in enumerate(cands, 1):
        sub = _clip_plan_to_window(plan, c)
        def cb(stage, pct, eta, _i=i, _n=len(cands)):
            # report per-short progress as a slice of the whole job
            base = (_i - 1) / _n * 100
            progress_cb(stage, base + pct / _n, eta)
        paths.append(run_render(project_id, "9:16", sub, cb,
                                output_name=f"short_{i}.mp4"))
    # persist candidate metadata next to the plan
    with open(os.path.join(project_dir(project_id),
                           "shorts_candidates.json"), "w") as f:
        json.dump(cands, f, indent=2)
    return paths
