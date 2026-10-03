"""Audio post-production filter sections (Worker C).

``post_chain(has_bgm, bgm_path, ducking=True)`` returns a *template* string
for the audio half of the render filtergraph plus the final audio label.

Template placeholders (filled by render_pipeline with .format):
  {VOICE}  label of the dialogue chain input (post intro/outro concat)
  {BGM}    label of the BGM input stream (ignored when has_bgm is False)
  {OUT}    label this section must produce

Chain (BGM on):
  voice: asplit -> (a) afftdn (light denoise) -> loudnorm I=-14 single-pass
                  (b) raw tap as the sidechain key (see note below)
  bgm:   volume 0.25 -> sidechaincompress keyed by the RAW voice tap
         (threshold 0.02, ratio 10, attack 200ms, release 800ms)
  mix:   amix voice+ducked bgm, duration=shortest (voice length; the BGM
         input is stream_looped/infinite so duration=first would NOT bound
         the tail — verified: duration=first let audio run 3x the video)

  NOTE (ffmpeg quirk, verified 2026-10-02): feeding the LOUDNORMED voice as
  the sidechaincompress key silently truncates the compressed BGM to the
  end of the last non-silent key segment (a 13.5s voice + 3s anullsrc outro
  came out 13.6s). The ducking key is only an envelope follower — it does
  not need normalization — so the key is tapped BEFORE afftdn/loudnorm.

Chain (no BGM): voice afftdn -> loudnorm only.

Chain (no BGM): voice afftdn -> loudnorm only.

BGM library: storage/assets/music/*.mp3 (Worker E generates 20+ tracks).
render_pipeline picks by plan music.track mood; if the file is missing or
Worker E hasn't generated it yet, has_bgm=False and a note is logged —
the render never fails for want of music.
"""

AUDIO_SECTION_TEMPLATE = (
    "[{VOICE}]asplit=2[{VOICE}_key][{VOICE}_mix];"
    "[{VOICE}_mix]afftdn=nf=-25:tn=1,loudnorm=I=-14:TP=-1.5:LRA=11[voice_clean];"
    "[{BGM}]volume=0.25[{BGM}_v];"
    "[{BGM}_v][{VOICE}_key]sidechaincompress=threshold=0.02:ratio=10"
    ":attack=200:release=800[bgm_duck];"
    "[voice_clean][bgm_duck]amix=inputs=2:duration=shortest"
    ":dropout_transition=0[{OUT}]"
)

AUDIO_SECTION_NO_BGM = (
    "[{VOICE}]afftdn=nf=-25:tn=1,loudnorm=I=-14:TP=-1.5:LRA=11[{OUT}]"
)


def post_chain(has_bgm: bool, bgm_path: str | None,
               ducking: bool = True) -> tuple[str, str]:
    """Return (filter_template, out_label_name).

    out_label_name is "a_out" in both cases; render_pipeline maps it.
    ducking=False keeps BGM at constant 0.25 (still mixed under voice).
    """
    if has_bgm and bgm_path:
        if not ducking:
            tmpl = AUDIO_SECTION_TEMPLATE.replace(
                "[{BGM}_v][{VOICE}_key]sidechaincompress=threshold=0.02"
                ":ratio=10:attack=200:release=800[bgm_duck]",
                "[{BGM}_v]anull[bgm_duck]",
            )
            return tmpl, "a_out"
        return AUDIO_SECTION_TEMPLATE, "a_out"
    return AUDIO_SECTION_NO_BGM, "a_out"


# ------------------------------------------------------------ BGM picking ---
import os

from .common import storage_dir

MOOD_KEYWORDS = {
    "energetic": ("energetic", "upbeat", "hype", "sport"),
    "calm": ("calm", "chill", "ambient", "lofi"),
    "cinematic": ("cinematic", "epic", "trailer", "dramatic"),
    "corporate": ("corporate", "business", "tech", "uplifting"),
}


def pick_bgm(track: str | None) -> tuple[str | None, str]:
    """Pick a BGM file from storage/assets/music by mood keyword.

    Returns (path_or_None, note). Never raises: missing library -> (None,
    note) and the caller renders voice-only.
    """
    music_dir = os.path.join(storage_dir("assets"), "music")
    try:
        files = sorted(f for f in os.listdir(music_dir)
                       if f.lower().endswith((".mp3", ".wav", ".m4a", ".ogg")))
    except OSError:
        files = []
    if not files:
        return None, "no BGM library yet (storage/assets/music empty) — voice only"
    want = (track or "corporate").lower()
    moods = MOOD_KEYWORDS.get(want, ())
    for f in files:
        if any(m in f.lower() for m in moods):
            return os.path.join(music_dir, f), f"matched mood '{want}'"
    return os.path.join(music_dir, files[0]), f"fallback to {files[0]}"
