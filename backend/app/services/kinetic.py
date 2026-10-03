"""Kinetic typography styles as ffmpeg drawtext filter strings (Worker C).

Each style is a function ``(text, t0, t1, W, H, palette, position="middle",
project_id="x", tag="k0") -> str`` returning a complete ``drawtext=...``
filter (chain) with ``enable='between(t,T0,T1)'``. Times are FINAL-timeline
seconds (render_pipeline adds the intro offset before calling).

Text is passed via ``textfile=`` (avoids inline escaping pain); fontfile is
always explicit (DejaVuSans-Bold). Every style fades alpha in/out over 0.25s.

Style -> animation expression (documented per function):
  scale_pop  fontsize = FS * ease_out_cubic(min(1,(t-T0)/0.25))
  slide_up   y falls from below frame to Y with quadratic ease-out
  slide_left x sweeps in from the right edge with quadratic ease-out
  typewriter drawtext (static) + drawbox mask whose left edge sweeps left,
             revealing characters left-to-right
  bounce     y = Y - |sin(9*(t-T0))| * 46 * exp(-3*(t-T0))  (damped bounce)
  glow_pulse alpha = fade_env * (0.55 + 0.45*sin(2*pi*2.2*(t-T0)))
  zoom_out   fontsize = FS * (1.35 - 0.35*min(1,(t-T0)/0.4))  (punch-out settle)

drawtext cannot blur text, so "blur-in" style requests are mapped to
glow_pulse (alpha pulse) by render_pipeline.
"""

import os

from .common import FONT_BOLD, asset_stage_dir, dt_escape, ff_escape, hex_to_ff


def _write_text_file(project_id: str, tag: str, text: str) -> str:
    d = asset_stage_dir(project_id)
    path = os.path.join(d, f"kinetic_{tag}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _base(textfile: str, t0: float, t1: float, palette: dict,
          fontsize_expr: str, x_expr: str, y_expr: str,
          alpha_expr: str | None = None,
          fontcolor: str | None = None, extra: str = "") -> str:
    color = fontcolor or hex_to_ff(palette.get("text", "#FFFFFF"))
    parts = [
        "drawtext",
        f"fontfile={ff_escape(FONT_BOLD)}",
        f"textfile={ff_escape(textfile)}",
        # fontsize/x/y/alpha are ALWAYS single-quoted: their expressions may
        # contain commas (min/max/pow), which would otherwise split options.
        f"fontsize='{fontsize_expr}'",
        f"fontcolor={color}",
        f"x='{x_expr}'",
        f"y='{y_expr}'",
        "borderw=3",
        f"bordercolor={hex_to_ff('#000000', 0.65)}",
        "shadowcolor=black@0.5", "shadowx=3", "shadowy=3",
    ]
    if alpha_expr:
        parts.append(f"alpha='{alpha_expr}'")
    if extra:
        parts.append(extra)
    parts.append(f"enable='between(t,{t0:.3f},{t1:.3f})'")
    # NOTE: filter name takes '=' (drawtext=...), ':' would be a parse error.
    return "drawtext=" + ":".join(parts[1:])


def _fade(t0: float, t1: float) -> str:
    # alpha envelope: 0.25s fade in/out, robust for short spans
    return (f"min(1,(t-{t0:.3f})/0.25)"
            f"*min(1,({t1:.3f}-t)/0.25)")


def _geom(W: int, H: int, position: str):
    fs = max(28, int(H * 0.075))
    y = {"top": H * 0.16, "middle": H * 0.42, "bottom": H * 0.74}[position]
    return fs, f"(w-text_w)/2", f"{y:.1f}"


def _prep(project_id, tag, text):
    return _write_text_file(project_id, tag, text)


# ------------------------------------------------------------------ styles ---
def scale_pop(text, t0, t1, W, H, palette, position="middle",
              project_id="render", tag="k"):
    """Scale-pop: fontsize grows 0 -> FS with cubic ease-out over 0.25s."""
    tf = _prep(project_id, tag, text)
    fs, x, y = _geom(W, H, position)
    pop = (f"{fs}*(1-pow(1-min(1,(t-{t0:.3f})/0.25),3))")
    return _base(tf, t0, t1, palette, pop, x, y, _fade(t0, t1))


def slide_up(text, t0, t1, W, H, palette, position="middle",
             project_id="render", tag="k"):
    """Slide-up: y starts one screen below and eases to Y (quadratic)."""
    tf = _prep(project_id, tag, text)
    fs, x, y = _geom(W, H, position)
    ye = f"({y})+({H:.0f}-({y}))*pow(max(0,1-(t-{t0:.3f})/0.35),2)"
    return _base(tf, t0, t1, palette, str(fs), x, ye, _fade(t0, t1))


def slide_left(text, t0, t1, W, H, palette, position="middle",
               project_id="render", tag="k"):
    """Slide-in from right: x sweeps from off-screen right (quadratic ease)."""
    tf = _prep(project_id, tag, text)
    fs, x, y = _geom(W, H, position)
    xe = (f"({x})+({W}-({x})+text_w+40)"
          f"*pow(max(0,1-(t-{t0:.3f})/0.35),2)")
    return _base(tf, t0, t1, palette, str(fs), xe, y, _fade(t0, t1))


def typewriter(text, t0, t1, W, H, palette, position="middle",
               project_id="render", tag="k"):
    """Typewriter: static drawtext + drawbox mask.

    The mask is a bg-coloured box anchored at the right edge whose LEFT edge
    sweeps left at constant speed, revealing the line left-to-right like
    typing. drawtext itself only gets the standard fade envelope.
    (drawbox cannot see drawtext's text_w, so the text width is measured
    with PIL at build time and baked into the expression as a number.)
    """
    tf = _prep(project_id, tag, text)
    fs, x, y = _geom(W, H, position)
    dt = _base(tf, t0, t1, palette, str(fs), x, y, _fade(t0, t1))
    dur = max(0.3, t1 - t0)
    bg = hex_to_ff(palette.get("bg", "#0B0B12"))
    try:
        from PIL import ImageFont
        tw = ImageFont.truetype(FONT_BOLD, fs).getlength(text)
    except Exception:
        tw = len(text) * fs * 0.6
    x0 = (W - tw) / 2  # centred text start, mirrors x='(w-text_w)/2'
    mask = (f"drawbox=x='{x0:.1f}+(({W}-{x0:.1f})*min(1,(t-{t0:.3f})/{dur:.3f}))'"
            f":y={float(y)-fs*0.25:.1f}:w='iw':h={fs*1.5:.0f}"
            f":color={bg}:t=fill:enable='between(t,{t0:.3f},{t1:.3f})'")
    return dt + "," + mask


def bounce(text, t0, t1, W, H, palette, position="middle",
           project_id="render", tag="k"):
    """Bounce: damped vertical oscillation settling onto Y."""
    tf = _prep(project_id, tag, text)
    fs, x, y = _geom(W, H, position)
    ye = (f"({y})-abs(sin(9*(t-{t0:.3f})))*46*exp(-3*(t-{t0:.3f}))")
    return _base(tf, t0, t1, palette, str(fs), x, ye, _fade(t0, t1))


def glow_pulse(text, t0, t1, W, H, palette, position="middle",
               project_id="render", tag="k"):
    """Glow-pulse: alpha throbs at ~2.2Hz inside the fade envelope.

    (drawtext cannot blur; this is the sanctioned stand-in for "blur-in".)
    """
    tf = _prep(project_id, tag, text)
    fs, x, y = _geom(W, H, position)
    a = (f"({_fade(t0, t1)})"
         f"*(0.55+0.45*sin(2*3.14159*2.2*(t-{t0:.3f})))")
    return _base(tf, t0, t1, palette, str(fs), x, y, a,
                 fontcolor=hex_to_ff(palette.get("accent", "#FFB020")))


def zoom_out(text, t0, t1, W, H, palette, position="middle",
             project_id="render", tag="k"):
    """Zoom-out settle: starts at 1.35x size, eases to FS over 0.4s."""
    tf = _prep(project_id, tag, text)
    fs, x, y = _geom(W, H, position)
    ze = f"{fs}*(1.35-0.35*min(1,(t-{t0:.3f})/0.4))"
    return _base(tf, t0, t1, palette, ze, x, y, _fade(t0, t1))


STYLES = {
    "scale_pop": scale_pop,
    "slide_up": slide_up,
    "slide_left": slide_left,
    "typewriter": typewriter,
    "bounce": bounce,
    "glow_pulse": glow_pulse,
    "zoom_out": zoom_out,
    # aliases the planner may emit
    "pop": scale_pop,
    "blur_in": glow_pulse,
    "fade": glow_pulse,
}


def kinetic_filter(style: str, text: str, t0: float, t1: float,
                   W: int, H: int, palette: dict, position: str = "middle",
                   project_id: str = "render", tag: str = "k") -> str:
    """Dispatch to a named style (unknown -> scale_pop)."""
    fn = STYLES.get((style or "").lower(), scale_pop)
    if position not in ("top", "middle", "bottom"):
        position = "middle"
    return fn(text, t0, t1, W, H, palette, position, project_id, tag)
