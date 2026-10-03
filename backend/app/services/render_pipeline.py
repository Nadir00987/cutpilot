"""Render orchestrator: plan -> ffmpeg filtergraph -> MP4 (Worker C).

``run_render(project_id, preset, plan, progress_cb, output_name=None) -> str``

Pipeline (single ffmpeg invocation, filtergraph written to
storage/projects/<pid>/filtergraph_<preset>.txt for auditability):

  1. validate plan (Worker B's validators.validate_plan, lazy import;
     fallback: local no-mid-word check) — violations fail loudly.
  2. cut kept spans (trim filter, frame-accurate), normalize each segment
     (scale/pad, fps=30, yuv420p, 48kHz stereo) -> concat. No black flashes:
     every segment is normalised BEFORE concat.
  3. aspect reframe (reframe.py): 16:9 presets scale-to-cover + crop;
     9:16/1:1 use blurred-background fill with face-anchored foreground.
  4. punch-in zooms (1.10-1.25x, smooth sin ramp) on emphasis spans,
     applied per-segment before concat (clipped to segment bounds).
  5. branded intro (2-3s PIL title card) + outro end card, concat n=3.
  6. b-roll overlays (overlay/takeover/split geometry, b-roll audio muted).
  7. PNG graphic overlays (lower thirds, callouts, ...) with alpha fades,
     enable=between on EDITED time (+ intro offset).
  8. drawtext kinetic headlines (>=6 styles, kinetic.py).
  9. progress bar (drawbox, width grows with t), watermark bug.
 10. ASS karaoke captions burned in (captions.py), toggleable.
 11. audio post: afftdn -> loudnorm -14 LUFS; BGM sidechain-ducked under
     voice (audio_post.py); b-roll contributes no audio.
 12. encode libx264 preset medium, crf 20, yuv420p, aac 192k, faststart.

All plan/analysis times are SOURCE time; this module maps them to edited
time through the kept spans: edited_t = source_t - removed_before(t).
"""

import datetime
import json
import os
import re
import subprocess

from .audio_post import pick_bgm, post_chain
from .broll import resolve_broll
from .captions import burn_filter, write_ass
from .common import (
    FONT_BOLD,
    asset_stage_dir,
    ff_escape,
    project_dir,
    repo_root,
    resolve_palette,
    storage_dir,
)
from .graphics import build_graphic, intro_card, outro_card, watermark
from .kinetic import kinetic_filter
from .reframe import detect_face_center, grab_frame, reframe_chain

PRESETS = {
    "1080p": (1920, 1080),
    "720p": (1280, 720),
    "4k": (3840, 2160),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
}
INTRO_DUR = 3.0
OUTRO_DUR = 3.0
FPS = 30


class RenderError(RuntimeError):
    pass


# ------------------------------------------------------------- validation ---
def _local_validate(plan: dict) -> None:
    """Fallback validator: hard no-mid-word rule + structural sanity."""
    cuts = _norm_cuts(plan.get("cuts") or [])
    if not cuts:
        raise RenderError("plan has no cuts")
    words = (plan.get("captions") or {}).get("words") or []
    bounds = []
    for w in words:
        bounds.extend([float(w["start"]), float(w["end"])])
    src_dur = float(plan.get("source_duration") or 0)
    tol = 0.15
    for s, e in cuts:
        if not e > s:
            raise RenderError(f"cut has end<=start: {s}-{e}")
        for t, name in ((s, "start"), (e, "end")):
            if t <= tol or (src_dur and abs(t - src_dur) <= 0.5):
                continue
            if not any(abs(t - b) <= tol for b in bounds):
                raise RenderError(
                    f"cut {name}={t:.2f}s is mid-word (no word boundary "
                    f"within {tol}s) — refusing to render")
    for i in range(1, len(cuts)):
        if cuts[i][0] < cuts[i - 1][1] - 1e-6:
            raise RenderError("cuts overlap")
    for g in plan.get("graphics") or []:
        if float(g.get("end", 0)) <= float(g.get("start", 0)):
            raise RenderError(f"graphic has end<=start: {g}")


def validate_plan_or_raise(plan: dict) -> None:
    """Worker B's validator when available, else the local no-mid-word check."""
    try:
        from app.services.validators import validate_plan as wb_validate
    except Exception:
        wb_validate = None
    if wb_validate is not None:
        wb_validate(plan)  # raises on violation -> fail loudly
    else:
        _local_validate(plan)


# ------------------------------------------------------------------ helpers ---
def _norm_cuts(cuts) -> list[tuple[float, float]]:
    out = []
    for c in cuts:
        if isinstance(c, (list, tuple)):
            s, e = float(c[0]), float(c[1])
        else:
            s, e = float(c["start"]), float(c["end"])
        out.append((s, e))
    return sorted(out)


def _ffprobe_duration(path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise RenderError(f"ffprobe could not read duration of {path}")


def _discover_source(project_id: str, plan: dict) -> str:
    sp = plan.get("source_path")
    if sp and os.path.exists(sp):
        return sp
    pj = os.path.join(project_dir(project_id), "project.json")
    if os.path.exists(pj):
        with open(pj) as f:
            cand = json.load(f).get("source_path")
        if cand and os.path.exists(cand):
            return cand
    for base in (project_dir(project_id),
                 os.path.join(repo_root(), "storage", "uploads", project_id)):
        if os.path.isdir(base):
            for fn in sorted(os.listdir(base)):
                if fn.lower().endswith((".mp4", ".mov", ".webm", ".mkv")):
                    return os.path.join(base, fn)
    raise RenderError(f"no source video found for project {project_id}")


class _TimeMap:
    """Source seconds -> edited seconds through kept spans."""

    def __init__(self, spans):
        self.spans = spans
        self.edited = sum(e - s for s, e in spans)

    def __call__(self, t: float) -> float:
        # kept footage before t (partial spans clipped)
        kept = 0.0
        for s, e in self.spans:
            kept += max(0.0, min(e, t) - s)
        return max(0.0, kept)

    def span_of(self, t: float):
        for i, (s, e) in enumerate(self.spans):
            if s - 1e-9 <= t <= e + 1e-9:
                return i
        return None


# ------------------------------------------------------------------ render ---
def run_render(project_id: str, preset: str, plan: dict, progress_cb,
               output_name: str | None = None) -> str:
    """Render the edit plan to MP4. Returns the output path."""
    if preset not in PRESETS:
        raise RenderError(f"unknown preset {preset!r} (want one of "
                          f"{sorted(PRESETS)})")
    validate_plan_or_raise(plan)

    TW, TH = PRESETS[preset]
    # working resolution: 16:9 presets normalise straight to target;
    # vertical/square normalise to 1920x1080 then reframe.
    WW, WH = (TW, TH) if preset in ("1080p", "720p", "4k") else (1920, 1080)

    source = _discover_source(project_id, plan)
    src_dur = float(plan.get("source_duration") or _ffprobe_duration(source))
    spans = _norm_cuts(plan.get("cuts") or [{"start": 0, "end": src_dur}])
    tmap = _TimeMap(spans)
    edited_dur = tmap.edited
    if edited_dur < 0.5:
        raise RenderError("edit is empty (all footage cut)")

    palette = resolve_palette(plan)
    brand_kit = plan.get("brand_kit") or {}
    io_cfg = plan.get("intro_outro") or {}
    intro_on = (io_cfg.get("intro") or {}).get("enabled", True)
    outro_on = (io_cfg.get("outro") or {}).get("enabled", True)
    intro_off = INTRO_DUR if intro_on else 0.0
    outro_dur = OUTRO_DUR if outro_on else 0.0
    total_dur = intro_off + edited_dur + outro_dur

    assets = asset_stage_dir(project_id)

    # ------------------------------------------------------- map plan times
    def emap(t):  # source -> final timeline (edited + intro offset)
        return tmap(t) + intro_off

    # captions words: keep words inside kept spans, map to edited time
    cap_cfg = plan.get("captions") or {}
    cap_words = []
    for w in cap_cfg.get("words") or []:
        s, e = float(w["start"]), float(w["end"])
        mid = (s + e) / 2
        if tmap.span_of(mid) is None:
            continue
        cap_words.append({"word": w["word"], "start": tmap(s), "end": tmap(e),
                          "emphasis": bool(w.get("emphasis"))})

    # punch-ins: graphics type punch-in/zoom (source time -> edited)
    punches = []  # (seg_idx, local_t0, local_t1, zoom)
    for g in plan.get("graphics") or []:
        if (g.get("type") or "").lower().replace("-", "_") not in (
                "punch_in", "zoom", "punchin"):
            continue
        s, e = tmap(float(g["start"])), tmap(float(g["end"]))
        if e - s < 0.3:
            continue
        zoom = float(g.get("zoom", 1.18))
        zoom = min(1.25, max(1.10, zoom))
        # clip to each affected segment (local times)
        acc = 0.0
        for i, (ss, ee) in enumerate(spans):
            seg_e = acc + (ee - ss)
            o0, o1 = max(s, acc), min(e, seg_e)
            if o1 - o0 >= 0.2:
                punches.append((i, o0 - acc, o1 - acc, zoom))
            acc = seg_e

    # b-roll specs (edited time; geometry resolved below)
    broll_specs = resolve_broll(
        plan, os.path.join(repo_root(), "storage", "assets", "broll"),
        time_map=tmap)

    # PNG graphics + kinetic + emoji (edited time)
    png_overlays = []   # (path, spec, t0, t1)
    kinetic_chains = []
    emoji_draws = []
    k_tag = 0
    for idx, g in enumerate(plan.get("graphics") or []):
        gt = (g.get("type") or "").lower().replace("-", "_")
        if gt in ("punch_in", "zoom", "punchin", "progress_bar"):
            continue
        s, e = tmap(float(g.get("start", 0))), tmap(float(g.get("end", 0)))
        if e - s < 0.15:
            continue
        t0, t1 = s + intro_off, e + intro_off
        text = g.get("text") or g.get("label") or ""
        if gt in ("kinetic", "headline", "kinetic_headline"):
            style = g.get("animation") or g.get("style") or (
                plan.get("style") or {}).get("kinetic_style", "scale_pop")
            kinetic_chains.append(kinetic_filter(
                style, text, t0, t1, TW, TH, palette,
                position=g.get("position", "middle"),
                project_id=project_id, tag=f"k{k_tag}"))
            k_tag += 1
        elif gt == "emoji":
            emoji_draws.append((text or "🔥", t0, t1,
                                g.get("position", "top_right")))
        else:
            path, spec = build_graphic(project_id, g, palette, tag=f"g{idx}")
            if path:
                png_overlays.append((path, spec, t0, t1))

    # progress bar: plan opt-in or explicit graphic; default ON
    style_cfg = plan.get("style") or {}
    want_progress = style_cfg.get("progress_bar", True) or any(
        (g.get("type") or "").lower() == "progress_bar"
        for g in plan.get("graphics") or [])

    # watermark
    wm_path, wm_spec = watermark(
        project_id, (brand_kit.get("logo_path") or plan.get("logo_path")),
        brand_kit.get("name", ""))

    # intro/outro cards
    intro_png = outro_png = None
    if intro_on:
        title = ((io_cfg.get("intro") or {}).get("title")
                 or plan.get("title") or "Untitled")
        intro_png = intro_card(project_id, brand_kit, title)
    if outro_on:
        outro_png = outro_card(project_id, brand_kit)

    # ------------------------------------------------------------- inputs
    # input 0 = source; then PNG overlays; intro/outro cards; b-roll; bgm
    cmd = ["ffmpeg", "-y", "-v", "error"]
    inputs = [("-i", source)]
    png_idx = {}
    for path, _s, _t0, _t1 in png_overlays:
        if path not in png_idx:
            png_idx[path] = len(inputs)
            inputs.append(("loop", path))
    if wm_path:
        wm_input = len(inputs)
        inputs.append(("loop", wm_path))
    intro_input = outro_input = None
    if intro_png:
        intro_input = len(inputs)
        inputs.append(("card", intro_png, INTRO_DUR))
    if outro_png:
        outro_input = len(inputs)
        inputs.append(("card", outro_png, OUTRO_DUR))
    broll_input = {}
    for bs in broll_specs:
        if bs["file"] and bs["file"] not in broll_input:
            broll_input[bs["file"]] = len(inputs)
            inputs.append(("broll", bs["file"]))
    bgm_path, bgm_note = (None, "bgm disabled in plan")
    music_cfg = plan.get("music") or {}
    if music_cfg.get("enabled", False):
        bgm_path, bgm_note = pick_bgm(music_cfg.get("track"))
    bgm_input = None
    if bgm_path:
        bgm_input = len(inputs)
        inputs.append(("bgm", bgm_path))

    for kind, *rest in inputs:
        if kind == "-i":
            cmd += ["-i", rest[0]]
        elif kind == "loop":
            # Bound looped PNG overlays to total_dur so EOF propagates cleanly
            # through overlay filters (infinite secondaries can stall EOF).
            cmd += ["-loop", "1", "-framerate", str(FPS),
                    "-t", f"{total_dur:.2f}", "-i", rest[0]]
        elif kind == "card":
            path, dur = rest
            cmd += ["-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.1f}",
                    "-i", path]
        elif kind == "broll":
            cmd += ["-stream_loop", "-1", "-i", rest[0]]
        elif kind == "bgm":
            cmd += ["-stream_loop", "-1", "-i", rest[0]]

    # ------------------------------------------------------- filter_complex
    F = []  # filter lines joined by ';'
    punch_by_seg = {}
    for seg_i, la, lb, zm in punches:
        punch_by_seg.setdefault(seg_i, []).append((la, lb, zm))

    for i, (s, e) in enumerate(spans):
        F.append(
            f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS,"
            f"scale={WW}:{WH}:force_original_aspect_ratio=decrease,"
            f"pad={WW}:{WH}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
            f"[p{i}]")
        vchain = []
        for la, lb, zm in punch_by_seg.get(i, []):
            dur = max(0.2, lb - la)
            zp = zm - 1.0
            prog = f"min(max((t-{la:.3f})/{dur:.3f},0),1)"
            z = f"(1+{zp:.3f}*sin(3.14159*{prog}))"
            vchain.append(
                f"scale=eval=frame:w='ceil(iw*{z})':h='ceil(ih*{z})',"
                f"crop=w={WW}:h={WH}:x='(in_w-{WW})/2':y='(in_h-{WH})/2'")
        vchain += [f"fps={FPS}", "format=yuv420p"]
        F.append(f"[p{i}]" + ",".join(vchain) + f"[pv{i}]")
        F.append(
            f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS,"
            f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
            f"[pa{i}]")

    cat_ins = "".join(f"[pv{i}][pa{i}]" for i in range(len(spans)))
    F.append(f"{cat_ins}concat=n={len(spans)}:v=1:a=1[catv][cata]")

    # reframe to the preset canvas (blurred-bg fill for 9:16 / 1:1)
    face = (0.5, 0.42)
    if preset in ("9:16", "1:1"):
        try:
            fp = os.path.join(assets, "face_probe.png")
            grab_frame(source, spans[0][0] + 0.5, fp)
            face = detect_face_center(fp)
        except Exception:
            pass
    F.append(f"[catv]{reframe_chain(preset, TW, TH, face)}[rfv]")

    # intro / outro concat (concat needs interleaved v,a,v,a,... inputs)
    if intro_on or outro_on:
        segs = []
        if intro_on:
            F.append(
                f"[{intro_input}:v]scale={TW}:{TH}:force_original_aspect_ratio"
                f"=increase,crop={TW}:{TH},fps={FPS},format=yuv420p[introv]")
            F.append(f"anullsrc=r=48000:cl=stereo:d={INTRO_DUR:.1f}[introa]")
            segs += ["[introv]", "[introa]"]
        segs += ["[rfv]", "[cata]"]
        if outro_on:
            F.append(
                f"[{outro_input}:v]scale={TW}:{TH}:force_original_aspect_ratio"
                f"=increase,crop={TW}:{TH},fps={FPS},format=yuv420p[outrov]")
            F.append(f"anullsrc=r=48000:cl=stereo:d={OUTRO_DUR:.1f}[outroa]")
            segs += ["[outrov]", "[outroa]"]
        n = len(segs) // 2
        F.append(f"{''.join(segs)}concat=n={n}:v=1:a=1[bv0][voice]")
    else:
        F.append("[rfv]null[bv0]")
        F.append("[cata]anull[voice]")

    bv = "bv0"
    n_ov = 0

    def _overlay_chain(video_label, overlay_label, x, y, t0, t1,
                       fade_in=0.25, fade_out=0.25):
        nonlocal bv, n_ov
        n_ov += 1
        fi, fo = max(0.01, fade_in), max(0.01, fade_out)
        F.append(
            f"[{overlay_label}]format=rgba,"
            f"fade=t=in:st={t0:.3f}:d={fi:.2f}:alpha=1,"
            f"fade=t=out:st={max(t0, t1 - fo):.3f}:d={fo:.2f}:alpha=1"
            f"[ov{n_ov}]")
        F.append(
            f"[{video_label}][ov{n_ov}]overlay=x={x}:y={y}:"
            f"enable='between(t,{t0:.3f},{t1:.3f})'[bv{n_ov}]")
        bv = f"bv{n_ov}"
        return bv

    # b-roll overlays (video only — b-roll audio always muted)
    for bi, bs in enumerate(broll_specs):
        if not bs["file"] or bs["mode"] == "keep":
            continue
        t0, t1 = bs["t0"] + intro_off, bs["t1"] + intro_off
        dur = t1 - t0
        inp = broll_input[bs["file"]]
        mode = bs["mode"]
        if mode == "takeover":
            geom = (f"scale={TW}:{TH}:force_original_aspect_ratio=increase,"
                    f"crop={TW}:{TH}")
            x, y = "0", "0"
        elif mode == "split":
            geom = (f"scale={TW // 2}:{TH}:force_original_aspect_ratio=increase,"
                    f"crop={TW // 2}:{TH}")
            x, y = "0", "0"
        else:  # overlay PiP
            pw = min(560, TW // 3)
            geom = f"scale={pw}:-2"
            x, y = f"W-w-40", f"H-h-220"
        F.append(
            f"[{inp}:v]trim=start=0:end={dur:.3f},setpts=PTS-STARTPTS,"
            f"{geom},format=yuv420p,"
            f"eq=contrast=1.05:saturation=1.1[br{bi}]")
        n_ov += 1
        F.append(
            f"[{bv}][br{bi}]overlay=x={x}:y={y}:"
            f"enable='between(t,{t0:.3f},{t1:.3f})'[bv{n_ov}]")
        bv = f"bv{n_ov}"

    # PNG graphic overlays
    for path, spec, t0, t1 in png_overlays:
        inp = png_idx[path]
        prep = f"[{inp}:v]"
        # pre-format is done inside _overlay_chain; just pass input label
        _overlay_chain(bv, f"{inp}:v", spec["x"], spec["y"], t0, t1,
                       spec.get("fade_in", 0.25), spec.get("fade_out", 0.25))

    # kinetic headlines (linear drawtext chains) + emoji + progress +
    # captions burn-in. Guard: if nothing to add, pass through with null.
    sub = []
    sub.extend(kinetic_chains)
    # emoji reactions as drawtext (DejaVu covers common symbols; colour
    # emoji glyphs may fall back to monochrome — documented limitation)
    for ei, (emo, t0, t1, pos) in enumerate(emoji_draws):
        epath = os.path.join(assets, f"emoji_{ei}.txt")
        with open(epath, "w", encoding="utf-8") as fh:
            fh.write(emo)
        ex = {"top_right": "W-220", "top_left": "60",
              "bottom_right": "W-220"}.get(pos, "W-220")
        ey = "120" if "top" in pos else "H-320"
        sub.append(
            f"drawtext=fontfile={ff_escape(FONT_BOLD)}:"
            f"textfile={ff_escape(epath)}:fontsize={int(TH * 0.09)}:"
            f"fontcolor=white:x={ex}:y={ey}:"
            f"alpha='min(1,(t-{t0:.3f})/0.2)*min(1,({t1:.3f}-t)/0.2)':"
            f"enable='between(t,{t0:.3f},{t1:.3f})'")
    if want_progress:
        accent = palette.get("accent", "#FFB020").lstrip("#")
        sub.append(
            f"drawbox=x=0:y=0:w='{TW}*t/{total_dur:.3f}':h=10:"
            f"color=0x{accent}:t=fill")
    if cap_cfg.get("enabled", True) and cap_words:
        ass_path = write_ass(
            cap_words, cap_cfg.get("style", "hormozi"), TW, TH,
            cap_cfg.get("position", "bottom"), project_id,
            tag=preset.replace(":", ""), time_offset=intro_off)
        sub.append(burn_filter(ass_path))
    if sub:
        F.append(f"[{bv}]" + ",".join(sub) + "[pre_wm]")
    else:
        F.append(f"[{bv}]null[pre_wm]")
    bv = "pre_wm"

    if wm_path:
        _overlay_chain(bv, f"{wm_input}:v", wm_spec["x"], wm_spec["y"],
                       0.0, total_dur, fade_in=0.0, fade_out=0.0)
    F.append(f"[{bv}]format=yuv420p[outv]")

    # audio post
    if bgm_input is not None:
        F.append(
            f"[{bgm_input}:a]atrim=0:{total_dur:.3f},asetpts=PTS-STARTPTS,"
            f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
            f"[bgm_pre]")
        tmpl, _ = post_chain(True, bgm_path,
                             ducking=music_cfg.get("ducking", True))
        F.append(tmpl.format(VOICE="voice", BGM="bgm_pre", OUT="a_out"))
    else:
        tmpl, _ = post_chain(False, None)
        F.append(tmpl.format(VOICE="voice", OUT="a_out"))

    filtergraph = ";\n".join(F) + "\n"

    # ------------------------------------------------------------- run
    date = datetime.datetime.now().strftime("%Y%m%d")
    safe_proj = "".join(c if c.isalnum() or c in "-_" else "_"
                        for c in project_id)[:40]
    safe_preset = preset.replace(":", "x")  # "9:16" -> "9x16" (no colon in filename)
    fname = output_name or f"{safe_proj}_{safe_preset}_{date}.mp4"
    out_dir = storage_dir("renders", project_id)
    out_path = os.path.join(out_dir, fname)

    cmd += ["-filter_complex", filtergraph,
            "-map", "[outv]", "-map", "[a_out]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            "-progress", "pipe:1", "-nostats", out_path]

    fg_path = os.path.join(project_dir(project_id), f"filtergraph_{preset}.txt")
    with open(fg_path, "w") as fh:
        fh.write(f"# CutPilot render filtergraph — project={project_id} "
                 f"preset={preset} date={date}\n")
        fh.write(f"# source={source}\n# bgm: {bgm_note}\n")
        fh.write(f"# total_dur={total_dur:.2f}s "
                 f"(intro={intro_off:.0f} edit={edited_dur:.2f} outro={outro_dur:.0f})\n")
        safe_cmd = []
        skip_next = False
        for a in cmd:
            if skip_next:
                safe_cmd.append("<filtergraph, see below>")
                skip_next = False
                continue
            if a == "-filter_complex":
                safe_cmd.append(a)
                skip_next = True
                continue
            safe_cmd.append(f"'{a}'" if " " in a else a)
        fh.write("# command:\n# " + " ".join(safe_cmd) + "\n\n")
        fh.write(filtergraph)
    with open(os.path.join(project_dir(project_id), "filtergraph.txt"), "w") as fh:
        fh.write(open(fg_path).read())

    progress_cb("rendering", 0.0, None)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True,
                            bufsize=1)
    total_us = max(1.0, total_dur * 1_000_000)
    start_ts = datetime.datetime.now().timestamp()
    pat = re.compile(r"out_time_ms=(\d+)")
    tail: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        tail.append(line.rstrip())
        if len(tail) > 40:
            tail.pop(0)
        m = pat.search(line)
        if m:
            # NOTE: despite the name, out_time_ms is in MICROSECONDS.
            out_time_us = float(m.group(1))
            pct = min(99.0, out_time_us / total_us * 100.0)
            elapsed = datetime.datetime.now().timestamp() - start_ts
            eta = (elapsed / max(pct, 0.5) * (100 - pct)) if pct > 0.5 else None
            progress_cb("rendering", round(pct, 1), eta)
    rc = proc.wait()
    if rc != 0:
        detail = "\n".join(tail[-15:])
        raise RenderError(f"ffmpeg exited {rc} for project {project_id}\n"
                          f"filtergraph: {fg_path}\nlast output:\n{detail}")
    progress_cb("rendering", 100.0, 0.0)

    # verify output
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=width,height,codec_name:format=duration",
         "-of", "json", out_path], capture_output=True, text=True)
    info = json.loads(r.stdout or "{}")
    streams = info.get("streams", [])
    vids = [s for s in streams if s.get("codec_name") == "h264"]
    auds = [s for s in streams if s.get("codec_name") == "aac"]
    if not vids or not auds:
        raise RenderError(f"render verification failed: {info}")
    return out_path
