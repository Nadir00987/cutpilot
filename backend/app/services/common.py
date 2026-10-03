"""Shared helpers for the CutPilot render engine (Worker C).

Centralises: font paths (explicit fontfile= everywhere — no fontconfig
guessing), ffmpeg argument escaping, palette resolution from the edit plan,
and storage path conventions.
"""

import os

# ---------------------------------------------------------------- fonts ---
# Explicit TTF paths — verified present on this VM via `fc-list`.
# drawtext and libass both receive explicit paths, so rendering never depends
# on fontconfig name resolution.
DEJAVU_DIR = "/usr/share/fonts/truetype/dejavu"
FONT_BOLD = os.path.join(DEJAVU_DIR, "DejaVuSans-Bold.ttf")
FONT_REGULAR = os.path.join(DEJAVU_DIR, "DejaVuSans.ttf")
FONT_MONO = os.path.join(DEJAVU_DIR, "DejaVuSansMono-Bold.ttf")
FONT_SERIF = os.path.join(DEJAVU_DIR, "DejaVuSerif.ttf")

ASS_FONT_BOLD = "DejaVu Sans"          # FontName used inside .ass files
ASS_FONT_MONO = "DejaVu Sans Mono"
ASS_FONTS_DIR = DEJAVU_DIR             # passed as fontsdir= to subtitles filter

for _p in (FONT_BOLD, FONT_REGULAR, FONT_MONO):
    if not os.path.exists(_p):
        raise RuntimeError(f"required font missing: {_p}")

# --------------------------------------------------------------- palette ---
DEFAULT_PALETTE = {
    "primary": "#7C5CFF",   # brand purple
    "accent": "#FFB020",    # warm amber
    "bg": "#0B0B12",        # near-black
    "text": "#FFFFFF",
}


def resolve_palette(plan: dict) -> dict:
    """Merge plan brand_kit/style colours over defaults.

    Accepts plan["brand_kit"]["colors"] and/or plan["style"]["palette"],
    tolerating either {"primary","accent","bg","text"} keys.
    """
    pal = dict(DEFAULT_PALETTE)
    for section in ("brand_kit", "style"):
        node = (plan.get(section) or {})
        colors = node.get("colors") or node.get("palette") or {}
        for k in ("primary", "accent", "bg", "text"):
            if colors.get(k):
                pal[k] = colors[k]
    return pal


def hex_to_ass(hex_color: str) -> str:
    """'#RRGGBB' -> ASS colour '&HAABBGGRR' (opaque)."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}".upper()


def hex_to_ff(hex_color: str, alpha: float = 1.0) -> str:
    """'#RRGGBB' -> ffmpeg colour '0xRRGGBB@alpha'."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return f"0x{h.upper()}@{alpha:g}"


# ------------------------------------------------------------------ misc ---
def ff_escape(s: str) -> str:
    """Escape a string for use inside a filter argument value.

    Escapes backslash first, then the filtergraph metacharacters.
    """
    return (
        str(s)
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace(":", "\\:")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace(";", "\\;")
    )


def dt_escape(s: str) -> str:
    """Escape literal text for drawtext text='...' (inline)."""
    return (
        str(s)
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("%", "\\%")
        .replace("\n", "\\n")
    )


def ass_escape(s: str) -> str:
    """Escape literal text for an ASS Dialogue line."""
    return str(s).replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


def fmt_ass_time(sec: float) -> str:
    """Seconds -> ASS timestamp 'H:MM:SS.cc'."""
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    cs = int(round((sec - int(sec)) * 100))
    if cs == 100:
        s += 1
        cs = 0
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def fmt_clock(sec: float) -> str:
    """Seconds -> 'MM:SS' chapter clock."""
    sec = max(0, int(sec))
    return f"{sec // 60:02d}:{sec % 60:02d}"


# --------------------------------------------------------------- storage ---
def repo_root() -> str:
    return os.path.expanduser("~/workspace/cutpilot-ai")


def storage_dir(*parts: str) -> str:
    p = os.path.join(repo_root(), "storage", *parts)
    os.makedirs(p, exist_ok=True)
    return p


def project_dir(project_id: str) -> str:
    return storage_dir("projects", project_id)


def asset_stage_dir(project_id: str) -> str:
    """Per-project scratch dir for generated PNGs/ASS/filtergraphs."""
    return storage_dir("projects", project_id, "render_assets")
