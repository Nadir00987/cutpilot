"""CutPilot AI — Stage C: automatic edit planner (RULES FIRST).

``build_edit_plan(analysis, style_opts, progress_cb=None) -> dict``

## Timebase convention (IMPORTANT — Worker C renderer, read this)

All ``start``/``end`` times in ``edit_plan.json`` — ``cuts``, ``graphics``,
``captions.words``, ``broll`` — are in **SOURCE time** (seconds from the
original upload). The renderer's job is to map source times through the
``cuts`` list to the edited timeline (a cut at source t that falls inside
kept span k maps to edited time ``t - offset_k`` where
``offset_k = sum of removed durations before k``). We chose source time so
the plan stays valid and auditable even when the user re-trims cuts in the
timeline editor: graphics stay glued to the words they were timed to.

## edit_plan.json schema (v1)

{
  "version": "1", "project_id": "<pid>", "source_duration": 30.5,
  "timebase": "source",
  "cuts": [{"start", "end", "reason"}],          # kept spans, source time
  "graphics": [{"type", "start", "end", "text", "style", "position",
                "reason", "editable", "x", "y"}],
  "captions": {"style", "position", "enabled",
               "words": [{"word", "start", "end", "emphasis"}]},
  "broll": [{"start", "end", "mode", "keyword", "source", "file",
             "prompt_suggestion"}],
      # mode: keep|overlay|split|takeover ; source: file|prompt_suggestion|none
      # file is set ONLY when the file exists on disk — never invented.
      # "none" means talking-head carries the beat (no B-roll).
  "music": {"track", "enabled", "ducking"},
  "audio": {"target_lufs": -14, "denoise": true},
  "intro_outro": {"intro": {"enabled", "style"}, "outro": {"enabled", "style"}},
  "brand_kit": {"primary_color", "font", "logo_path"},
  "style": {merged style_opts},
  "shorts": [{"start", "end", "title", "reason"}],
  "chapters": [{"start", "title"}],
  "reorder_suggestions": [],
  "notes": []
}

## Hard rules

- Never cut mid-word: every cut boundary is snapped to the nearest word
  boundary with 80-120 ms padding (pad = min(0.12, gap/2), never < 80 ms).
- ``validators.validate_plan`` must pass on the output before render
  (Worker C MUST call it — see validators.py).
- Every decision object carries ``reason`` (auditability = quality bar).
"""

from __future__ import annotations

import os
import re

PAD_MIN, PAD_MAX = 0.08, 0.12
EPS = 1e-3


# ---------------------------------------------------------------- cut logic

def _removal_spans(analysis: dict) -> list[tuple[float, float, str]]:
    spans: list[tuple[float, float, str]] = []
    for s in analysis.get("silences", []):
        spans.append((s["start"], s["end"],
                      f"Silence {s['duration']}s removed (threshold exceeded)."))
    for f in analysis.get("fillers", []):
        if f.get("action") == "cut":
            spans.append((f["start"], f["end"],
                          f"{f['type'].replace('_', ' ').title()} '{f.get('word', '')}' cut."))
    # merge overlapping / adjacent spans
    spans.sort()
    merged: list[list] = []
    for s, e, r in spans:
        if merged and s <= merged[-1][1] + 0.05:
            merged[-1][1] = max(merged[-1][1], e)
            merged[-1][2] += " + " + r
        else:
            merged.append([s, e, r])
    return [(s, e, r) for s, e, r in merged]


def _kept_spans(duration: float, removals: list[tuple[float, float, str]]
                ) -> list[tuple[float, float, str]]:
    kept = []
    cursor = 0.0
    for s, e, reason in removals:
        if s > cursor + EPS:
            kept.append((cursor, s,
                         f"Kept speech after removing: {reason}"))
        cursor = max(cursor, e)
    if cursor < duration - EPS:
        kept.append((cursor, duration, "Kept speech (final span)."))
    # drop degenerate spans
    kept = [k for k in kept if k[1] - k[0] > 0.25]
    return kept


def _snap_boundary(b: float, words: list[dict], side: str) -> float:
    """Move cut boundary ``b`` outside every word span with >=80ms padding.

    side='start' -> boundary is the START of a kept span (push right).
    side='end'   -> boundary is the END of a kept span (push left).
    pad = min(0.12, gap/2) but never < 0.08; iterated to convergence.
    """
    for _ in range(25):
        moved = False
        for idx, w in enumerate(words):
            ws, we = w["start"], w["end"]
            if ws < EPS and b < PAD_MIN:
                # boundary at/near t=0: allow exactly 0
                if side == "start":
                    b = 0.0
                    break
            violates = (ws + PAD_MIN - 1e-6 < b < we - PAD_MIN + 1e-6) or \
                       (abs(b - ws) < PAD_MIN - 1e-6) or (abs(b - we) < PAD_MIN - 1e-6)
            if not violates:
                continue
            if side == "start":
                gap = (words[idx + 1]["start"] - we) if idx + 1 < len(words) else 1.0
                pad = max(PAD_MIN, min(PAD_MAX, gap / 2))
                b = we + pad
            else:
                gap = (ws - words[idx - 1]["end"]) if idx > 0 else 1.0
                pad = max(PAD_MIN, min(PAD_MAX, gap / 2))
                b = ws - pad
            moved = True
            break
        if not moved:
            break
    return max(0.0, round(b, 3))


def _snap_cuts(kept: list[tuple[float, float, str]], words: list[dict],
               duration: float) -> list[dict]:
    words_sorted = sorted(words, key=lambda w: w["start"])
    out = []
    for s, e, reason in kept:
        s2 = 0.0 if s <= PAD_MIN else _snap_boundary(s, words_sorted, "start")
        e2 = duration if duration - e <= PAD_MIN else _snap_boundary(e, words_sorted, "end")
        if e2 - s2 < 0.25:
            continue  # collapsed by snapping; drop
        out.append({"start": s2, "end": round(e2, 3), "reason": reason})
    # merge any spans that now overlap
    out.sort(key=lambda c: c["start"])
    merged = []
    for c in out:
        if merged and c["start"] <= merged[-1]["end"] + EPS:
            merged[-1]["end"] = max(merged[-1]["end"], c["end"])
            merged[-1]["reason"] += " | merged after word-boundary snapping"
        else:
            merged.append(c)
    return merged


def _split_for_pacing(cuts: list[dict], words: list[dict],
                      pacing: str) -> list[dict]:
    """Energetic pacing: split long kept spans at sentence/phrase boundaries
    to target ~3-4s shots. Otherwise keep breathing room (min 6s)."""
    if pacing != "energetic":
        return cuts
    target = 3.5
    out = []
    for c in cuts:
        dur = c["end"] - c["start"]
        if dur <= 6.0:
            out.append(c)
            continue
        # find phrase boundaries (word ends followed by punctuation or pause)
        bounds = [c["start"]]
        prev_end = None
        for w in sorted(words, key=lambda x: x["start"]):
            if not (c["start"] <= w["start"] and w["end"] <= c["end"]):
                continue
            txt = w["word"]
            if prev_end is not None and w["start"] - prev_end > 0.45:
                bounds.append(w["start"])          # pause boundary
            elif txt and txt[-1] in ".!?,":
                bounds.append(w["end"] + 0.001)    # sentence boundary
            prev_end = w["end"]
        bounds.append(c["end"])
        bounds = sorted(set(round(b, 3) for b in bounds))
        # greedy merge into ~3.5s shots
        shots, cur = [], bounds[0]
        for b in bounds[1:]:
            if b - cur >= target and cur > bounds[0]:
                shots.append((cur, b)); cur = b
            elif b - cur >= target * 1.6:
                shots.append((cur, b)); cur = b
        shots.append((cur, bounds[-1]))
        shots = [(s, e) for s, e in shots if e - s > 0.4]
        for i, (s, e) in enumerate(shots):
            out.append({"start": s, "end": e,
                        "reason": c["reason"] + f" | energetic pacing shot {i+1}/{len(shots)}"})
    return out


# ---------------------------------------------------------------- graphics

GRAPHIC_DEFAULTS = {
    "kinetic_headline": {"position": "middle", "x": 0.5, "y": 0.42, "editable": True},
    "lower_third":      {"position": "bottom", "x": 0.08, "y": 0.82, "editable": True},
    "callout":          {"position": "middle", "x": 0.5, "y": 0.30, "editable": True},
    "punch_in":         {"position": "full",   "x": 0.5, "y": 0.5,  "editable": False},
    "progress_bar":     {"position": "top",    "x": 0.5, "y": 0.02, "editable": False},
    "emoji_reaction":   {"position": "corner", "x": 0.88, "y": 0.12, "editable": True},
    "quote_card":       {"position": "middle", "x": 0.5, "y": 0.5,  "editable": True},
    "stat_popup":       {"position": "middle", "x": 0.5, "y": 0.35, "editable": True},
    "subscribe":        {"position": "middle", "x": 0.5, "y": 0.55, "editable": True},
}


def _build_graphics(analysis: dict, cuts: list[dict], style: dict) -> list[dict]:
    g: list[dict] = []
    words = analysis.get("words", [])
    keywords = analysis.get("keywords", [])[:8]
    kinetic_style = style.get("kinetic_style", "pop_word")
    emoji_on = style.get("emoji_on", True)

    def add(gtype, start, end, text, reason, style_override=None, **kw):
        d = GRAPHIC_DEFAULTS[gtype]
        g.append({
            "type": gtype, "start": round(start, 3), "end": round(end, 3),
            "text": text, "style": style_override or kinetic_style,
            "position": d["position"], "reason": reason,
            "editable": d["editable"], "x": d["x"], "y": d["y"], **kw,
        })

    # kinetic headlines on top keywords (timed to the spoken phrase)
    for k in keywords[:5]:
        add("kinetic_headline", k["start"], k["end"], k["phrase"].upper(),
            f"Top keyword (score {k['score']}) — karaoke-style emphasis timed to speech.")

    # lower third on first speaker appearance
    if words:
        first = words[0]
        spk = analysis.get("speakers", [{}])[0].get("label", "Speaker 1") \
            if analysis.get("speakers") else "Speaker 1"
        add("lower_third", first["start"], first["start"] + 4.0,
            analysis.get("suggested_title", spk)[:40],
            f"Name/title card on first appearance of {spk}.",
            style_override="lower_third_default")

    # punch-ins on emphasis words, max 1 per 8s, 110-125% zoom
    emph_times = sorted({k["start"] for k in keywords})
    last = -99.0
    for t in emph_times:
        if t - last >= 8.0:
            add("punch_in", t, t + 0.6, "zoom 115%",
                "Punch-in 115% on emphasis word — draws the eye to the key point.",
                style_override="zoom_115")
            last = t

    # stat popups for numbers in speech
    num_re = re.compile(r"\b\d+[%x]?\b")
    for w in words[:400]:
        if num_re.search(w["word"]):
            add("stat_popup", w["start"], w["start"] + 1.5, w["word"],
                f"Number '{w['word']}' spoken — stat popup reinforces the figure.")
            break

    # quote card: strongest (highest-energy) sentence
    segs = sorted(analysis.get("segments", []),
                  key=lambda s: s.get("energy", 0), reverse=True)
    if segs:
        q = segs[0]
        add("quote_card", q["start"], q["start"] + 3.0, q["text"][:90],
            f"Highest-energy sentence (energy {q.get('energy')}) — quote card for shareability.")

    # emoji reactions on energy spikes
    if emoji_on:
        for h in analysis.get("highlights", [])[:4]:
            emoji = "🔥" if h["energy"] >= 85 else "⚡"
            add("emoji_reaction", h["start"], h["start"] + 1.2, emoji,
                f"Energy spike ({h['energy']}) — context-matched reaction, toggleable.")

    # progress bar across the edit
    if cuts:
        add("progress_bar", cuts[0]["start"], cuts[-1]["end"], "",
            "Brand-color progress bar across the whole edit.",
            style_override=style.get("palette", {}).get("primary", "#7C3AED")
            if isinstance(style.get("palette"), dict) else "#7C3AED")

    # subscribe CTA near the end
    dur = analysis["source"]["duration"]
    add("subscribe", max(0.0, dur - 8.0), dur, "Subscribe!",
        "Subscribe animation in the final 8s — end-card CTA.")

    g.sort(key=lambda x: x["start"])
    return g


# ---------------------------------------------------------------- captions / broll / music

def _build_captions(analysis: dict, cuts: list[dict], style: dict) -> dict:
    kw_unigrams = set()
    for k in analysis.get("keywords", []):
        kw_unigrams.update(k["phrase"].lower().split())

    def in_kept(w) -> bool:
        mid = (w["start"] + w["end"]) / 2
        return any(c["start"] - EPS <= mid <= c["end"] + EPS for c in cuts)

    words = []
    for w in analysis.get("words", []):
        if not in_kept(w):
            continue
        clean = re.sub(r"[^\w']", "", w["word"]).lower()
        words.append({
            "word": w["word"], "start": w["start"], "end": w["end"],
            "emphasis": clean in kw_unigrams,
        })
    return {
        "style": style.get("caption_style", "hormozi_bold"),
        "position": style.get("caption_position", "bottom"),
        "enabled": style.get("captions_on", True),
        "words": words,
    }


def _words_in(words: list[dict], s: float, e: float) -> list[dict]:
    return [w for w in words if w["start"] >= s - EPS and w["end"] <= e + EPS]


def _build_broll(analysis: dict, cuts: list[dict], style: dict) -> list[dict]:
    words = analysis.get("words", [])
    keywords = analysis.get("keywords", [])
    broll_dir = style.get("broll_dir", "")
    files: list[str] = []
    if broll_dir and os.path.isdir(broll_dir):
        for f in sorted(os.listdir(broll_dir)):
            if f.lower().endswith((".mp4", ".mov", ".webm", ".mkv")):
                files.append(os.path.join(broll_dir, f))

    items = []
    for c in cuts:
        seg_words = _words_in(words, c["start"], c["end"])
        dur = c["end"] - c["start"]
        density = len(seg_words) / dur if dur else 0
        energy_vals = [p["energy"] for p in analysis.get("energy_profile", [])
                       if p["end"] > c["start"] and p["start"] < c["end"]]
        energy = sum(energy_vals) / len(energy_vals) if energy_vals else 50
        seg_text = " ".join(w["word"] for w in seg_words).lower()
        kw = next((k["phrase"] for k in keywords if k["phrase"].lower() in seg_text), "")

        if density < 0.5 and dur > 3:
            mode, reason = "takeover", (
                f"Low speech density ({density:.1f} w/s) — full B-roll takeover "
                "keeps visual interest during dead air.")
        elif energy >= 70 or sum(1 for k in keywords if k["phrase"].lower() in seg_text) >= 3:
            mode, reason = "overlay", (
                f"High energy ({energy:.0f}) / keyword-dense — B-roll overlay "
                "under the talking head.")
        elif kw:
            mode, reason = "split", (
                f"Keyword '{kw}' illustrated — split-screen B-roll.")
        else:
            mode, reason = "keep", "Talking head carries this beat — no B-roll."

        item = {"start": c["start"], "end": c["end"], "mode": mode,
                "keyword": kw, "reason": reason, "source": None,
                "file": None, "prompt_suggestion": None}
        if mode != "keep":
            if files:
                item["source"] = "file"
                item["file"] = files[0]
                item["reason"] += f" Using user B-roll file {os.path.basename(files[0])}."
            else:
                item["source"] = "prompt_suggestion"
                item["prompt_suggestion"] = (
                    f"Cinematic B-roll: {kw or 'abstract motion background'}, "
                    f"16:9, shallow depth of field, professional color grade, "
                    f"no text, {dur:.0f} seconds")
                item["reason"] += " No stock match — AI B-roll prompt suggested instead of irrelevant footage."
        else:
            item["source"] = "none"
        items.append(item)
    return items


MOOD_TRACKS = {
    "energetic": "upbeat_energy_01",
    "calm": "chill_vlog_01",
    "cinematic": "cinematic_pad_01",
    "corporate": "corporate_clean_01",
}


def _build_shorts(analysis: dict, cuts: list[dict]) -> list[dict]:
    duration = analysis["source"]["duration"]
    win = min(45.0, max(15.0, duration * 0.6))
    candidates = []
    t = 0.0
    while t + 15.0 <= duration:
        e = min(t + win, duration)
        kept_frac = sum(max(0.0, min(c["end"], e) - max(c["start"], t))
                        for c in cuts) / (e - t)
        if kept_frac >= 0.6:
            prof = [p for p in analysis.get("energy_profile", [])
                    if p["end"] > t and p["start"] < e]
            energy = sum(p["energy"] for p in prof) / len(prof) if prof else 50
            ws = [w["word"] for w in analysis.get("words", [])
                  if t <= w["start"] < e][:12]
            candidates.append({
                "start": round(t, 2), "end": round(e, 2),
                "title": " ".join(ws).strip(" ,.")[:50] or "Highlight",
                "score": energy * kept_frac,
                "reason": (f"High-energy {e - t:.0f}s window "
                           f"(avg energy {energy:.0f}, {kept_frac:.0%} kept speech) — "
                           "shorts-ready clip."),
            })
        t += 10.0
    candidates.sort(key=lambda c: -c["score"])
    picked, out = [], []
    for c in candidates:
        if all(c["end"] <= p["start"] or c["start"] >= p["end"] for p in picked):
            picked.append(c)
            out.append({k: c[k] for k in ("start", "end", "title", "reason")})
        if len(out) >= 3:
            break
    return out


# ---------------------------------------------------------------- main entry

def build_edit_plan(analysis: dict, style_opts: dict,
                    progress_cb=None) -> dict:
    """Build the edit plan (rules-first) from ``analysis`` + ``style_opts``.

    style_opts keys (all optional, defaults shown):
      template_id="talking_head", kinetic_style="pop_word",
      caption_style="hormozi_bold", caption_position="bottom",
      palette={"primary": "#7C3AED"}, pacing="natural" | "energetic",
      emoji_on=True, captions_on=True, broll_dir="",
      music_track=None, music_enabled=True,
      brand_kit={"primary_color","font","logo_path"},
      intro_enabled=False, outro_enabled=True
    """
    def progress(pct, stage):
        if progress_cb:
            try:
                progress_cb(pct, stage)
            except Exception:  # noqa: BLE001
                pass

    style = {
        "template_id": "talking_head",
        "kinetic_style": "pop_word",
        "caption_style": "hormozi_bold",
        "caption_position": "bottom",
        "palette": {"primary": "#7C3AED"},
        "pacing": "natural",
        "emoji_on": True,
        "captions_on": True,
        "broll_dir": "",
        "music_track": None,
        "music_enabled": True,
        "brand_kit": {"primary_color": "#7C3AED", "font": "Inter", "logo_path": None},
        "intro_enabled": False,
        "outro_enabled": True,
    }
    style.update(style_opts or {})
    if isinstance(style_opts.get("brand_kit"), dict):
        merged_bk = dict(style["brand_kit"]); merged_bk.update(style_opts["brand_kit"])
        style["brand_kit"] = merged_bk

    notes: list[str] = []
    duration = analysis["source"]["duration"]
    words = analysis.get("words", [])

    # 1. cuts ----------------------------------------------------------------
    progress(15, "cuts")
    removals = _removal_spans(analysis)
    kept = _kept_spans(duration, removals)
    if not kept:  # degenerate: keep everything rather than output nothing
        kept = [(0.0, duration, "No removable spans — full video kept.")]
        notes.append("No silences/fillers to cut — full duration kept.")
    cuts = _snap_cuts(kept, words, duration)
    cuts = _split_for_pacing(cuts, words, style["pacing"])
    kept_dur = sum(c["end"] - c["start"] for c in cuts)
    notes.append(f"Removed {duration - kept_dur:.1f}s of {duration:.1f}s "
                 f"({len(cuts)} kept spans, all boundaries snapped to word edges).")
    # 2. graphics -------------------------------------------------------------
    progress(40, "graphics")
    graphics = _build_graphics(analysis, cuts, style)

    # 3. captions -------------------------------------------------------------
    progress(60, "captions")
    captions = _build_captions(analysis, cuts, style)

    # 4. b-roll ---------------------------------------------------------------
    progress(75, "broll")
    broll = _build_broll(analysis, cuts, style)

    # 5. music / audio / packaging --------------------------------------------
    progress(88, "packaging")
    mood = "energetic" if style["pacing"] == "energetic" else "calm"
    music = {
        "track": style["music_track"] or MOOD_TRACKS[mood],
        "enabled": style["music_enabled"],
        "ducking": True,
        "reason": f"Track '{style['music_track'] or MOOD_TRACKS[mood]}' matches "
                  f"'{mood}' mood for {style['pacing']} pacing; auto-ducked under speech.",
    }
    audio = {"target_lufs": -14, "denoise": True,
             "reason": "Normalize to -14 LUFS (YouTube/social standard); "
                       "afftdn denoise for consistent voice."}
    intro_outro = {
        "intro": {"enabled": style["intro_enabled"], "style": "brand_reveal_2s",
                  "reason": "Optional 2s branded intro."},
        "outro": {"enabled": style["outro_enabled"], "style": "end_card_subscribe",
                  "reason": "End card with subscribe CTA."},
    }

    shorts = _build_shorts(analysis, cuts)
    if not shorts:
        notes.append("No shorts extracted: no 15s+ window with >=60% kept "
                     "speech and above-average energy found.")

    plan = {
        "version": "1",
        "project_id": analysis["project_id"],
        "source_duration": duration,
        "timebase": "source",
        "cuts": cuts,
        "graphics": graphics,
        "captions": captions,
        "broll": broll,
        "music": music,
        "audio": audio,
        "intro_outro": intro_outro,
        "brand_kit": style["brand_kit"],
        "style": {k: v for k, v in style.items() if k != "brand_kit"},
        "shorts": shorts,
        "chapters": analysis.get("chapters", []),
        "reorder_suggestions": [],
        "notes": notes + ["Chronological order kept; reorder only on user approval."],
    }
    progress(100, "done")
    return plan
