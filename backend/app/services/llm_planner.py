"""CutPilot AI — optional LLM refinement pass over the edit plan.

``refine_with_llm(plan, analysis) -> dict``

When an LLM is configured, it may improve graphics timing/copy and caption
emphasis. When not configured this is a documented no-op: the rules-first
plan is returned unchanged with a note. Worker C may call this after
``build_edit_plan`` and before ``validators.validate_plan``.
"""

from __future__ import annotations

import copy
import json

from .stages.llm import chat, LLMNotConfigured, llm_available


def refine_with_llm(plan: dict, analysis: dict) -> dict:
    plan = copy.deepcopy(plan)
    if not llm_available():
        plan.setdefault("notes", []).append(
            "LLM not configured — plan unchanged (rules-first output kept).")
        return plan
    try:
        out = chat([
            {"role": "system",
             "content": (
                 "You are a senior video editor. You receive an auto-generated "
                 "edit plan (JSON) plus the video summary. Improve ONLY the "
                 "graphics list: tighten copy (max 6 words per text), fix "
                 "awkward timings, remove redundant graphics. Keep every "
                 "time in SOURCE seconds, keep all other keys identical. "
                 "Reply with JSON {\"graphics\": [...]} using the same object "
                 "shape (type,start,end,text,style,position,reason,editable,x,y)."
             )},
            {"role": "user",
             "content": json.dumps({
                 "graphics": plan.get("graphics", []),
                 "summary": analysis.get("summary", ""),
                 "duration": analysis.get("source", {}).get("duration", 0),
             })},
        ], json_mode=True)
        data = json.loads(out)
        if isinstance(data.get("graphics"), list) and data["graphics"]:
            plan["graphics"] = data["graphics"]
            plan.setdefault("notes", []).append(
                "Graphics timing/copy refined by LLM.")
        else:
            plan.setdefault("notes", []).append(
                "LLM returned no usable graphics — rules-first plan kept.")
    except (LLMNotConfigured, Exception) as e:  # noqa: BLE001
        plan.setdefault("notes", []).append(
            f"LLM refinement skipped ({type(e).__name__}) — rules-first plan kept.")
    return plan
