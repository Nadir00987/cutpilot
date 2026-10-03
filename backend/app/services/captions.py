"""Styled ASS caption writer with word-level karaoke highlight (Worker C).

``write_ass(words, style_name, W, H, position, project_id="x", tag="cap",
time_offset=0.0)`` writes an .ass file and returns its path. Words are
``[{word, start, end, emphasis?}]`` in FINAL-timeline seconds (render_pipeline
adds the intro offset via ``time_offset``).

Each Dialogue line holds max 5 words (or ~2.4s), broken at word boundaries.
The active word is highlighted with ``{\\k<centiseconds>}`` karaoke tags;
emphasis words additionally get an inline colour override.

10 named styles: hormozi, minimal, karaoke, outline, bold_pop, mono,
elegant, neon, caption_box, tiktok. Burn-in via the ``subtitles`` filter
with ``fontsdir=`` pointing at DejaVu so libass resolves FontName without
fontconfig.
"""

import os

from .common import (
    ASS_FONT_BOLD,
    ASS_FONT_MONO,
    ASS_FONTS_DIR,
    ass_escape,
    asset_stage_dir,
    ff_escape,
    fmt_ass_time,
    hex_to_ass,
)

# name -> {FontName, scale (x height), Primary, Outline, Back, Bold, Italic,
#          OutlineW, ShadowD, align_default}
STYLES = {
    "hormozi": dict(font=ASS_FONT_BOLD, scale=0.062, primary="#FFFFFF",
                    outline="#000000", back="#000000", bold=-1, italic=0,
                    ow=3.0, sh=1.5, align=2),
    "minimal": dict(font=ASS_FONT_BOLD, scale=0.042, primary="#FFFFFF",
                    outline="#000000", back="#000000", bold=0, italic=0,
                    ow=1.2, sh=0.8, align=2),
    "karaoke": dict(font=ASS_FONT_BOLD, scale=0.055, primary="#8A8A8A",
                    outline="#000000", back="#000000", bold=-1, italic=0,
                    ow=2.5, sh=1.2, align=2, karaoke_color="#FFD23F"),
    "outline": dict(font=ASS_FONT_BOLD, scale=0.058, primary="#000000",
                    outline="#FFFFFF", back="#000000", bold=-1, italic=0,
                    ow=1.5, sh=0, align=2),
    "bold_pop": dict(font=ASS_FONT_BOLD, scale=0.068, primary="#FFD23F",
                     outline="#7A2E00", back="#000000", bold=-1, italic=0,
                     ow=3.5, sh=2.0, align=5),
    "mono": dict(font=ASS_FONT_MONO, scale=0.046, primary="#D8FFD8",
                 outline="#0A0A0A", back="#0A0A0A", bold=-1, italic=0,
                 ow=1.5, sh=1.0, align=2),
    "elegant": dict(font="DejaVu Serif", scale=0.052, primary="#FFF8E7",
                    outline="#2A1E0A", back="#000000", bold=0, italic=-1,
                    ow=1.5, sh=1.0, align=2),
    "neon": dict(font=ASS_FONT_BOLD, scale=0.058, primary="#39FF88",
                 outline="#00331A", back="#000000", bold=-1, italic=0,
                 ow=2.0, sh=0, align=2, karaoke_color="#FFFFFF"),
    "caption_box": dict(font=ASS_FONT_BOLD, scale=0.048, primary="#FFFFFF",
                        outline="#000000", back="#000000", bold=-1, italic=0,
                        ow=1.0, sh=0, align=2, box=True),
    "tiktok": dict(font=ASS_FONT_BOLD, scale=0.06, primary="#FFFFFF",
                   outline="#000000", back="#000000", bold=-1, italic=0,
                   ow=2.5, sh=1.5, align=2),
}

POSITION_ALIGN = {"top": 8, "middle": 5, "bottom": 2}


def _chunk(words, max_words=5, max_dur=2.4):
    """Group words into caption lines: <=max_words and <=max_dur seconds."""
    lines, cur = [], []
    for w in words:
        cur.append(w)
        dur = cur[-1]["end"] - cur[0]["start"]
        if len(cur) >= max_words or dur >= max_dur:
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    return lines


def _karaoke_line(line, style, time_offset):
    """One Dialogue event with \\k tags; returns (start, end, text)."""
    parts = []
    kc = hex_to_ass(style.get("karaoke_color", "#FFD23F"))
    for w in line:
        dur_cs = max(1, int(round((w["end"] - w["start"]) * 100)))
        txt = ass_escape(w["word"])
        if w.get("emphasis"):
            # emphasis: accent colour + bold karaoke sweep
            parts.append(f"{{\\k{dur_cs}\\c{kc}\\b1}}{txt}{{\\r}}")
        elif "karaoke_color" in style or style.get("karaoke_always"):
            parts.append(f"{{\\k{dur_cs}}}{txt}")
        else:
            parts.append(f"{{\\k{dur_cs}}}{txt}")
    # hormozi/minimal/etc: karaoke sweep still uses \\k (active word fill);
    # the sweep colour comes from SecondaryColour.
    start = line[0]["start"] + time_offset
    end = line[-1]["end"] + time_offset + 0.12  # tiny hold
    return start, end, "".join(parts)


def write_ass(words: list, style_name: str, W: int, H: int,
              position: str = "bottom", project_id: str = "render",
              tag: str = "cap", time_offset: float = 0.0) -> str:
    """Write styled karaoke .ass; return path."""
    style = STYLES.get((style_name or "").lower(), STYLES["hormozi"])
    align = POSITION_ALIGN.get(position, style["align"])
    size = max(20, int(H * style["scale"]))

    words = sorted(words, key=lambda w: w["start"])
    lines = _chunk(words)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: cap,{style['font']},{size},{hex_to_ass(style['primary'])},{hex_to_ass(style.get('karaoke_color', '#FFD23F'))},{hex_to_ass(style['outline'])},{hex_to_ass(style['back'])},{style['bold']},{style['italic']},0,0,100,100,0,0,{'3' if style.get('box') else '1'},{style['ow']},{style['sh']},{align},40,40,{max(24, int(H*0.045))},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for line in lines:
        s, e, text = _karaoke_line(line, style, time_offset)
        events.append(
            f"Dialogue: 0,{fmt_ass_time(s)},{fmt_ass_time(e)},cap,,0,0,0,,{text}")

    d = asset_stage_dir(project_id)
    path = os.path.join(d, f"captions_{tag}.ass")
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events) + "\n")
    return path


def burn_filter(ass_path: str) -> str:
    """subtitles filter string with explicit fontsdir (no fontconfig)."""
    return (f"subtitles={ff_escape(ass_path)}"
            f":fontsdir={ff_escape(ASS_FONTS_DIR)}")


def available_styles() -> list:
    return sorted(STYLES)
