"""PIL motion-graphic asset builders (Worker C).

Every function renders a transparent PNG into the project's render_assets
dir and returns ``(png_path, spec)`` where spec is an overlay spec consumed
by render_pipeline::

    spec = {"x": int|expr, "y": int|expr, "w": int, "h": int,
            "fade_in": 0.25, "fade_out": 0.25}

x/y may be plain ints or ffmpeg overlay expressions (e.g. "(W-w)/2",
"W-w-40"). render_pipeline applies ``format=rgba`` + alpha fades and
``overlay=...:enable='between(t,T0,T1)'``.

All builders take ``palette`` = {"primary","accent","bg","text"} hex dict
(from plan brand_kit/style via common.resolve_palette).
"""

import os
import textwrap

from PIL import Image, ImageDraw, ImageFont

from .common import (
    FONT_BOLD,
    FONT_MONO,
    FONT_REGULAR,
    asset_stage_dir,
    resolve_palette,
)

# ------------------------------------------------------------------ utils ---
def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _fit_font(draw: ImageDraw.ImageDraw, text: str, path: str, max_w: int,
              start: int) -> ImageFont.FreeTypeFont:
    """Largest font size <= start that fits text within max_w."""
    size = start
    while size > 12:
        f = _font(path, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 2
    return _font(path, 12)


def _rgba(hex_color: str, alpha: int = 255):
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


def _save(img: Image.Image, project_id: str, name: str) -> str:
    d = asset_stage_dir(project_id)
    path = os.path.join(d, f"{name}.png")
    img.save(path)
    return path


def _wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# ------------------------------------------------------------ lower third ---
def lower_third(project_id: str, title: str, subtitle: str = "",
               palette: dict | None = None, tag: str = "lt") -> tuple[str, dict]:
    """Name/title card: accent bar + dark pill with title + subtitle.

    Returns PNG 1100x200; spec anchors bottom-left of frame.
    """
    pal = resolve_palette({"style": {"palette": palette or {}}})
    W, H = 1100, 200
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # backdrop pill
    d.rounded_rectangle([10, 10, W - 10, H - 10], radius=28,
                        fill=_rgba(pal["bg"], 225))
    # accent bar
    d.rounded_rectangle([10, 10, 34, H - 10], radius=12, fill=_rgba(pal["accent"]))
    # thin top highlight
    d.rounded_rectangle([10, 10, W - 10, 22], radius=11, fill=(255, 255, 255, 28))

    f_title = _fit_font(d, title, FONT_BOLD, W - 140, 64)
    d.text((70, 34), title, font=f_title, fill=_rgba(pal["text"]))
    if subtitle:
        f_sub = _fit_font(d, subtitle, FONT_REGULAR, W - 140, 40)
        d.text((72, 118), subtitle, font=f_sub, fill=_rgba(pal["accent"]))

    path = _save(img, project_id, f"{tag}_lower_third")
    spec = {"x": 60, "y": "H-h-90", "w": W, "h": H,
            "fade_in": 0.3, "fade_out": 0.3}
    return path, spec


# ------------------------------------------------------------ callout box ---
def callout_box(project_id: str, label: str, style: str = "highlight",
               palette: dict | None = None, tag: str = "co") -> tuple[str, dict]:
    """Annotation graphic. style in {"arrow","circle","highlight","pill"}.

    * arrow:     label pill + left-pointing arrow tab
    * circle:    accent ring (drawn around an empty centre) + label below
    * highlight: marker-style translucent band sized to the label
    * pill:      simple rounded label pill
    """
    pal = resolve_palette({"style": {"palette": palette or {}}})
    style = style if style in ("arrow", "circle", "highlight", "pill") else "highlight"

    tmp = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    d0 = ImageDraw.Draw(tmp)
    f = _fit_font(d0, label, FONT_BOLD, 900, 56)
    tw = int(d0.textlength(label, font=f)) + 80
    th = 110

    if style == "circle":
        S = 420
        img = Image.new("RGBA", (S, S + 130), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse([18, 18, S - 18, S - 18], outline=_rgba(pal["accent"]), width=14)
        fl = _fit_font(d, label, FONT_BOLD, S - 40, 52)
        lw = d.textlength(label, font=fl)
        d.text(((S - lw) / 2, S + 18), label, font=fl, fill=_rgba(pal["text"]))
        path = _save(img, project_id, f"{tag}_callout_circle")
        return path, {"x": "(W-w)/2", "y": "(H-h)/2", "w": img.width,
                      "h": img.height, "fade_in": 0.2, "fade_out": 0.2}

    W = max(tw, 220)
    H = th + (70 if style == "arrow" else 0)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    if style == "highlight":
        d.rounded_rectangle([6, 18, W - 6, th - 6], radius=26,
                            fill=_rgba(pal["accent"], 200))
        d.text(((W - d.textlength(label, font=f)) / 2, 32), label,
               font=f, fill=(20, 16, 8, 255))
    elif style == "pill":
        d.rounded_rectangle([6, 6, W - 6, th - 6], radius=40,
                            fill=_rgba(pal["bg"], 230),
                            outline=_rgba(pal["accent"]), width=5)
        d.text(((W - d.textlength(label, font=f)) / 2, 26), label,
               font=f, fill=_rgba(pal["text"]))
    else:  # arrow
        d.rounded_rectangle([60, 6, W - 6, th - 6], radius=30,
                            fill=_rgba(pal["primary"], 235))
        d.polygon([(60, 20), (60, th - 20), (8, th // 2)], fill=_rgba(pal["primary"]))
        lw = d.textlength(label, font=f)
        d.text((60 + (W - 60 - lw) / 2, 26), label, font=f,
               fill=_rgba(pal["text"]))

    path = _save(img, project_id, f"{tag}_callout_{style}")
    spec = {"x": "(W-w)/2", "y": "H*0.30", "w": W, "h": H,
            "fade_in": 0.2, "fade_out": 0.2}
    return path, spec


# ----------------------------------------------------------- progress bar ---
def progress_bar(project_id: str, w: int = 1920, color: str = "#FFB020",
                 tag: str = "pb") -> tuple[str, dict]:
    """Full-width thin progress bar PNG (decorative track + fill).

    Note: render_pipeline normally draws the progress bar with a drawbox
    whose width grows with time (cheaper, perfectly smooth). This PNG is for
    styled variants requested explicitly by the plan.
    """
    H = 26
    img = Image.new("RGBA", (w, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 6, w, H - 6], radius=7, fill=(255, 255, 255, 60))
    d.rounded_rectangle([0, 6, w, H - 6], radius=7, fill=_rgba(color))
    path = _save(img, project_id, f"{tag}_progress")
    return path, {"x": 0, "y": "H-h", "w": w, "h": H,
                  "fade_in": 0.0, "fade_out": 0.0}


# ------------------------------------------------------------ quote card ----
def quote_card(project_id: str, text: str, palette: dict | None = None,
               tag: str = "qc") -> tuple[str, dict]:
    """Centred testimonial/quote card, 1000x560."""
    pal = resolve_palette({"style": {"palette": palette or {}}})
    W, H = 1000, 560
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8, 8, W - 8, H - 8], radius=44, fill=_rgba(pal["bg"], 235),
                        outline=_rgba(pal["accent"]), width=6)
    fq = _font(FONT_SERIF, 150)
    d.text((60, 30), "\u201c", font=fq, fill=_rgba(pal["accent"], 160))
    fb = _fit_font(d, text, FONT_BOLD, W - 160, 54)
    lines = _wrap(d, text, fb, W - 160)
    lh = fb.size + 18
    y = 190
    for ln in lines[:6]:
        lw = d.textlength(ln, font=fb)
        d.text(((W - lw) / 2, y), ln, font=fb, fill=_rgba(pal["text"]))
        y += lh
    path = _save(img, project_id, f"{tag}_quote")
    return path, {"x": "(W-w)/2", "y": "(H-h)/2", "w": W, "h": H,
                  "fade_in": 0.3, "fade_out": 0.3}


# ------------------------------------------------------------ stat popup ---
def stat_popup(project_id: str, text: str, palette: dict | None = None,
               tag: str = "sp") -> tuple[str, dict]:
    """Big-number stat popup, 640x360, accent ring."""
    pal = resolve_palette({"style": {"palette": palette or {}}})
    W, H = 640, 360
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8, 8, W - 8, H - 8], radius=48, fill=_rgba(pal["bg"], 240))
    d.rounded_rectangle([8, 8, W - 8, H - 8], radius=48,
                        outline=_rgba(pal["primary"]), width=8)
    f = _fit_font(d, text, FONT_BOLD, W - 120, 110)
    lw = d.textlength(text, font=f)
    d.text(((W - lw) / 2, (H - f.size) / 2 - 10), text, font=f,
           fill=_rgba(pal["accent"]))
    path = _save(img, project_id, f"{tag}_stat")
    return path, {"x": "(W-w)/2", "y": "H*0.28", "w": W, "h": H,
                  "fade_in": 0.2, "fade_out": 0.2}


# ---------------------------------------------------------- subscribe bug --
def subscribe_bug(project_id: str, palette: dict | None = None,
                  tag: str = "sb") -> tuple[str, dict]:
    """YouTube-style SUBSCRIBE pill, 360x120, bottom-right anchor."""
    pal = resolve_palette({"style": {"palette": palette or {}}})
    W, H = 360, 120
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([6, 6, W - 6, H - 6], radius=56, fill=(204, 0, 0, 235))
    f = _font(FONT_BOLD, 52)
    label = "SUBSCRIBE"
    lw = d.textlength(label, font=f)
    d.text(((W - lw) / 2, 30), label, font=f, fill=(255, 255, 255, 255))
    path = _save(img, project_id, f"{tag}_subscribe")
    return path, {"x": "W-w-50", "y": "H-h-170", "w": W, "h": H,
                  "fade_in": 0.3, "fade_out": 0.3}


# ---------------------------------------------------------- intro / outro ---
def _brand_title(project_id, brand_kit, title, name, size_hint=1.0):
    pal = resolve_palette({"brand_kit": brand_kit or {}})
    W, H = 1920, 1080
    img = Image.new("RGBA", (W, H), _rgba(pal["bg"]))
    d = ImageDraw.Draw(img)
    # soft radial-ish vignette bands
    for i, a in enumerate((26, 18, 12)):
        inset = 60 + i * 130
        d.rounded_rectangle([inset, inset, W - inset, H - inset], radius=90,
                            outline=_rgba(pal["primary"], a), width=3)
    # accent underline bar
    bar_w = 420
    d.rounded_rectangle([(W - bar_w) / 2, H * 0.60, (W + bar_w) / 2, H * 0.60 + 14],
                        radius=7, fill=_rgba(pal["accent"]))
    fb = _fit_font(d, title, FONT_BOLD, W - 320, int(150 * size_hint))
    lw = d.textlength(title, font=fb)
    d.text(((W - lw) / 2, H * 0.38), title, font=fb, fill=_rgba(pal["text"]))
    brand = (brand_kit or {}).get("name", "")
    if brand:
        fs = _font(FONT_REGULAR, 54)
        bw = d.textlength(brand, font=fs)
        d.text(((W - bw) / 2, H * 0.68), brand, font=fs,
               fill=_rgba(pal["accent"]))
    path = _save(img, project_id, name)
    return path


def intro_card(project_id: str, brand_kit: dict | None, title: str) -> str:
    """2–3s branded title card (1920x1080; scaled to preset in filtergraph)."""
    return _brand_title(project_id, brand_kit, title, "intro_card")


def outro_card(project_id: str, brand_kit: dict | None) -> str:
    """End card with subscribe CTA (1920x1080)."""
    pal = resolve_palette({"brand_kit": brand_kit or {}})
    path = _brand_title(project_id, brand_kit, "Thanks for watching",
                        "outro_card", size_hint=0.8)
    img = Image.open(path).convert("RGBA")
    d = ImageDraw.Draw(img)
    W, H = img.size
    f = _font(FONT_BOLD, 58)
    cta = "Subscribe for more"
    lw = d.textlength(cta, font=f)
    d.rounded_rectangle([(W - lw) / 2 - 50, H * 0.66, (W + lw) / 2 + 50,
                         H * 0.66 + 110], radius=55, fill=(204, 0, 0, 255))
    d.text(((W - lw) / 2, H * 0.66 + 22), cta, font=f, fill=(255, 255, 255, 255))
    img.save(path)
    return path


# ------------------------------------------------------------- watermark ---
def watermark(project_id: str, logo_path: str | None = None,
              brand_name: str = "") -> tuple[str, dict] | tuple[None, None]:
    """Small logo/text bug for the corner. Returns (None, None) if no logo
    and no brand name — render_pipeline then skips the watermark."""
    if logo_path and os.path.exists(logo_path):
        logo = Image.open(logo_path).convert("RGBA")
        h = 72
        w = int(logo.width * h / logo.height)
        logo = logo.resize((w, h), Image.LANCZOS)
        pad = 18
        img = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
        img.alpha_composite(logo, (pad, pad))
    elif brand_name:
        f = _font(FONT_BOLD, 44)
        tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10), (0, 0, 0, 0)))
        tw = int(tmp.textlength(brand_name, font=f)) + 56
        img = Image.new("RGBA", (tw, 96), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([4, 4, tw - 4, 92], radius=46, fill=(0, 0, 0, 110))
        d.text((28, 22), brand_name, font=f, fill=(255, 255, 255, 200))
    else:
        return None, None
    path = _save(img, project_id, "watermark")
    spec = {"x": "W-w-36", "y": "H-h-36", "w": img.width, "h": img.height,
            "fade_in": 0.0, "fade_out": 0.0}
    return path, spec


# ------------------------------------------------------- plan-driven build --
GRAPHIC_BUILDERS = {
    "lower_third": lower_third,
    "callout": callout_box,
    "quote": quote_card,
    "stat": stat_popup,
    "subscribe": subscribe_bug,
    "progress_bar": progress_bar,
}


def build_graphic(project_id: str, item: dict, palette: dict,
                  tag: str) -> tuple[str | None, dict | None]:
    """Build a PNG asset for one plan graphics[] item.

    item: {type, text, ...}. Unknown types -> (None, None) (skipped, logged).
    Emoji items are handled as drawtext by render_pipeline; this only builds
    PNG-backed types.
    """
    gtype = (item.get("type") or "").lower()
    text = item.get("text") or item.get("label") or ""
    try:
        if gtype == "lower_third":
            return lower_third(project_id, text, item.get("subtitle", ""),
                               palette, tag=tag)
        if gtype in ("callout", "annotation"):
            return callout_box(project_id, text, item.get("style", "highlight"),
                               palette, tag=tag)
        if gtype in ("quote", "quote_card"):
            return quote_card(project_id, text, palette, tag=tag)
        if gtype in ("stat", "stat_popup"):
            return stat_popup(project_id, text, palette, tag=tag)
        if gtype in ("subscribe", "subscribe_bug"):
            return subscribe_bug(project_id, palette, tag=tag)
        if gtype == "progress_bar":
            return progress_bar(project_id, color=palette.get("accent", "#FFB020"),
                                tag=tag)
    except Exception:
        return None, None
    return None, None
