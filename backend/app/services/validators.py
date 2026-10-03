"""CutPilot AI — edit-plan validators.

Worker C's renderer MUST call ``validate_plan(plan)`` before render and
refuse to render when ``ok`` is False.

Checks:
  1. No mid-word cuts — every cut boundary must be >= 80 ms outside every
     word span (MASTER_PROMPT §7: "No mid-word cuts. Ever.").
  2. Timeline coverage — kept spans are sorted, non-overlapping and inside
     [0, duration], so their concatenation (the edited timeline) has no gaps
     (no black flashes). Gaps BETWEEN kept spans in source time are the
     intentional cuts and are expected.
  3. Plan schema sanity — required keys, timebase == "source", sane times.
"""

from __future__ import annotations

PAD = 0.08   # 80 ms minimum clearance
EPS = 0.05   # coverage tolerance


def validate_no_midword_cuts(plan: dict, words: list[dict]) -> list[dict]:
    """Return violations: [{boundary, word, word_start, word_end, side}]."""
    violations: list[dict] = []
    for i, c in enumerate(plan.get("cuts", [])):
        for side, b in (("start", c["start"]), ("end", c["end"])):
            # t=0 and t=duration boundaries are exempt by construction
            if (side == "start" and b <= EPS) or \
               (side == "end" and abs(b - plan.get("source_duration", 0)) <= EPS):
                continue
            for w in words:
                ws, we = w["start"], w["end"]
                inside = (ws + PAD - 1e-9 < b < we - PAD + 1e-9)
                touching = abs(b - ws) < PAD - 1e-9 or abs(b - we) < PAD - 1e-9
                if inside or touching:
                    violations.append({
                        "cut_index": i, "side": side, "boundary": b,
                        "word": w["word"], "word_start": ws, "word_end": we,
                    })
                    break  # one violation per boundary is enough
    return violations


def assert_no_midword_cuts(plan: dict, words: list[dict]) -> None:
    violations = validate_no_midword_cuts(plan, words)
    if violations:
        raise ValueError(f"Mid-word cut violations: {violations[:5]}")


def validate_timeline_coverage(plan: dict, duration: float) -> list[dict]:
    """Kept spans must tile the EDITED timeline: sorted, non-overlapping,
    all inside [0, duration].

    Note on timebase: ``cuts`` are kept spans in SOURCE time, so gaps between
    them are expected — those gaps are the intentional cuts (removed
    silences/fillers), which the renderer skips. Concatenating the kept spans
    therefore yields a continuous edited timeline with no black flashes, as
    long as the kept spans themselves are sorted and never overlap. That is
    what this check enforces.
    """
    errors: list[dict] = []
    cuts = sorted(plan.get("cuts", []), key=lambda c: c["start"])
    if not cuts:
        return [{"check": "coverage", "error": "cuts list is empty"}]
    for i, c in enumerate(cuts):
        if c["start"] < -EPS or c["end"] > duration + EPS:
            errors.append({"check": "coverage",
                           "error": f"cut {i} [{c['start']}-{c['end']}] outside [0, {duration}]"})
    for i, (a, b) in enumerate(zip(cuts, cuts[1:])):
        gap = b["start"] - a["end"]
        if gap < -EPS:
            errors.append({"check": "coverage",
                           "error": f"overlap {-gap:.3f}s between cuts "
                                    f"[{a['start']}-{a['end']}] and [{b['start']}-{b['end']}]"})
    return errors


def validate_plan(plan: dict) -> dict:
    """Run all checks. Returns {"ok": bool, "errors": [...]}."""
    errors: list[dict] = []
    for key in ("version", "project_id", "source_duration", "timebase",
                "cuts", "graphics", "captions", "broll", "music", "audio", "style"):
        if key not in plan:
            errors.append({"check": "schema", "error": f"missing key '{key}'"})
    if plan.get("timebase") != "source":
        errors.append({"check": "schema",
                       "error": f"timebase must be 'source', got {plan.get('timebase')!r}"})
    duration = plan.get("source_duration", 0) or 0
    for i, c in enumerate(plan.get("cuts", [])):
        if not (0 <= c["start"] < c["end"] <= duration + EPS):
            errors.append({"check": "schema",
                           "error": f"cut {i} has invalid span [{c['start']}, {c['end']}]"})
    # mid-word check needs words — captions carry the edited word list
    cap_words = plan.get("captions", {}).get("words", [])
    if cap_words:
        for v in validate_no_midword_cuts(plan, cap_words):
            errors.append({"check": "midword_cut", **v})
    errors.extend(validate_timeline_coverage(plan, duration))
    return {"ok": not errors, "errors": errors}
