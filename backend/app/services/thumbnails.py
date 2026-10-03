"""Thumbnail generator (Worker C).

``generate_thumbnails(project_id, analysis=None, source_path=None)`` -> 3 PNG
paths in storage/thumbnails/<pid>/thumb_{1,2,3}.png.

Pipeline per thumbnail: grab a frame at a hook/high-energy timestamp ->
PIL composition in one of 3 styles (bold_contrast, minimal, split).

Source discovery (Worker A integration): explicit ``source_path`` wins;
else storage/projects/<pid>/project.json {"source_path": ...}; else the
first video file under storage/projects/<pid>/ or storage/uploads/<pid>/.
Analysis likewise from the ``analysis`` arg or analysis.json. Times fall
back to 8%/25%/50% of duration.
"""

import json
import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

from .common import FONT_BOLD, FONT_REGULAR, project_dir, storage_dir

VIDEO_EXTS = (".mp4", ".mov", ".webm", ".mkv")
TW, TH = 1280, 720


def _discover(project_id: str, analysis, source_path):
    if analysis is None:
        ap = os.path.join(project_dir(project_id), "analysis.json")
        if os.path.exists(ap):
            with open(ap) as f:
                analysis = json.load(f)
    if source_path is None:
        pj = os.path.join(project_dir(project_id), "project.json")
        if os.path.exists(pj):
            with open(pj) as f:
                source_path = json.load(f).get("source_path")
    if not source_path:
        for base in (project_dir(project_id),
                     os.path.join(storage_dir("uploads"), project_id)):
            if os.path.isdir(base):
                for fn in sorted(os.listdir(base)):
                    if fn.lower().endswith(VIDEO_EXTS):
                        source_path = os.path.join(base, fn)
                        break
            if source_path:
                break
    if not source_path:
        raise FileNotFoundError(
            f"no source video found for project {project_id}")
    return analysis or {}, source_path


def _duration(path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 30.0


def _hook_times(analysis: dict, duration: float) -> list[float]:
    segs = analysis.get("segments") or []
    if segs:
        ranked = sorted(segs, key=lambda s: s.get("energy", 50), reverse=True)
        times = [float(s.get("start", 0)) + 0.5 for s in ranked[:3]]
    else:
        times = [duration * 0.08, duration * 0.25, duration * 0.5]
    return [min(max(0.5, t), max(1.0, duration - 1.0)) for t in times]


def _grab(video: str, at: float, dest: str) -> str:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{at:.2f}", "-i", video,
         "-frames:v", "1", "-vf", f"scale={TW}:{TH}:force_original_aspect_ratio=increase,"
         f"crop={TW}:{TH}", dest], check=True)
    return dest


def _texts(analysis: dict) -> list[str]:
    ts = analysis.get("thumbnail_texts") or []
    if len(ts) >= 3:
        return ts[:3]
    title = (analysis.get("title") or analysis.get("summary") or
             "Watch this").split(".")[0]
    base = [t.strip() for t in ts] + [title.strip()]
    while len(base) < 3:
        base.append(title.strip())
    return [t[:42] for t in base[:3]]


def _font(size):
    return ImageFont.truetype(FONT_BOLD, size)


def _wrap(d, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= max_w:
            cur = t
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return [l for l in lines if l]


def _style_bold_contrast(frame: Image.Image, text: str) -> Image.Image:
    img = frame.convert("RGBA")
    d = ImageDraw.Draw(img)
    # bottom gradient for legibility
    grad = Image.new("L", (1, TH))
    for y in range(TH):
        grad.putpixel((0, y), int(200 * max(0, (y - TH * 0.35) / (TH * 0.65))))
    grad = grad.resize((TW, TH))
    img.putalpha(Image.composite(
        Image.new("L", (TW, TH), 255), Image.new("L", (TW, TH), 180), grad))
    img = img.convert("RGB")
    d = ImageDraw.Draw(img)
    f = _font(120)
    lines = _wrap(d, text.upper(), f, TW - 120)[:2]
    y = TH - 60 - len(lines) * 140
    for ln in lines:
        lw = d.textlength(ln, font=f)
        x = (TW - lw) / 2
        for ox, oy in ((-4, 0), (4, 0), (0, -4), (0, 4)):
            d.text((x + ox, y + oy), ln, font=f, fill=(0, 0, 0))
        d.text((x, y), ln, font=f, fill=(255, 210, 63))
        y += 140
    return img


def _style_minimal(frame: Image.Image, text: str) -> Image.Image:
    img = frame.convert("RGB")
    d = ImageDraw.Draw(img)
    d.rectangle([0, TH - 190, TW, TH], fill=(8, 8, 12))
    f = ImageFont.truetype(FONT_REGULAR, 64)
    lines = _wrap(d, text, f, TW - 160)[:2]
    y = TH - 170
    for ln in lines:
        d.text((80, y), ln, font=f, fill=(245, 245, 245))
        y += 78
    return img


def _style_split(frame: Image.Image, text: str) -> Image.Image:
    img = Image.new("RGB", (TW, TH), (12, 10, 24))
    right = frame.resize((TW // 2, TH))
    img.paste(right, (TW // 2, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 40, TH], fill=(255, 176, 32))
    f = _font(96)
    lines = _wrap(d, text.upper(), f, TW // 2 - 140)[:3]
    y = 150
    for ln in lines:
        d.text((90, y), ln, font=f, fill=(255, 255, 255),
               stroke_width=3, stroke_fill=(0, 0, 0))
        y += 112
    return img


def generate_thumbnails(project_id: str, analysis: dict | None = None,
                        source_path: str | None = None) -> list[str]:
    """Generate 3 styled thumbnails -> list of PNG paths."""
    analysis, source = _discover(project_id, analysis, source_path)
    duration = _duration(source)
    times = _hook_times(analysis, duration)
    texts = _texts(analysis)
    styles = [_style_bold_contrast, _style_minimal, _style_split]
    out_dir = storage_dir("thumbnails", project_id)
    paths = []
    for i, (sty, t, txt) in enumerate(zip(styles, times, texts), 1):
        raw = os.path.join(out_dir, f"_frame_{i}.png")
        _grab(source, t, raw)
        frame = Image.open(raw).convert("RGB")
        out = os.path.join(out_dir, f"thumb_{i}.png")
        sty(frame, txt or "Watch this").save(out)
        os.remove(raw)
        paths.append(out)
    return paths
