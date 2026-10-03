#!/usr/bin/env python3
"""Generate 24 original procedural background-music tracks with ffmpeg.

Each track is synthesized from scratch (layered sine oscillators: chord pads,
arpeggios, sub bass) — no samples, no third-party audio — so every track is
original by construction and safe to bundle royalty-free.

Categories: energetic x6, calm x6, cinematic x6, corporate x6.
Specs: 30s, 44.1 kHz stereo MP3, loudness-normalized (-16 LUFS).

Output: assets/music/<category>_<nn>.mp3  (+ manifest.json)
        also copied to storage/assets/music/ as seed data.

Runtime: ~24 ffmpeg invocations, well under 10 minutes.
"""
import json
import math
import os
import random
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(REPO, "assets", "music")
SEED_DIR = os.path.join(REPO, "storage", "assets", "music")
TRACK_SEC = 30.0
CHORD_SEC = TRACK_SEC / 4  # 4 chords per track


def midi_to_freq(midi: int) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


# Progressions as (root_offset_semitones, chord_quality) relative to track root.
# quality: "maj" or "min" triad built on the offset.
PROGRESSIONS = {
    "energetic": [
        [(0, "maj"), (7, "maj"), (9, "min"), (5, "maj")],     # I V vi IV
        [(0, "maj"), (5, "maj"), (9, "min"), (7, "maj")],     # I IV vi V
        [(9, "min"), (5, "maj"), (0, "maj"), (7, "maj")],     # vi IV I V
    ],
    "calm": [
        [(0, "maj"), (4, "min"), (5, "maj"), (7, "maj")],     # I iii IV V
        [(9, "min"), (5, "maj"), (0, "maj"), (4, "min")],     # vi IV I iii
        [(0, "maj"), (9, "min"), (5, "maj"), (7, "maj")],     # I vi IV V
    ],
    "cinematic": [
        [(0, "min"), (8, "maj"), (3, "maj"), (10, "maj")],    # i VI III VII
        [(0, "min"), (5, "min"), (8, "maj"), (7, "maj")],     # i v VI VII
        [(0, "min"), (10, "maj"), (8, "maj"), (7, "maj")],    # i VII VI V
    ],
    "corporate": [
        [(0, "maj"), (7, "maj"), (9, "min"), (5, "maj")],     # I V vi IV
        [(0, "maj"), (5, "maj"), (7, "maj"), (4, "min")],     # I IV V iii
        [(5, "maj"), (0, "maj"), (9, "min"), (7, "maj")],     # IV I vi V
    ],
}

CATEGORY_PARAMS = {
    # bpm, arp subdivision of a beat, pad brightness (lowpass Hz), arp volume
    "energetic":  {"bpm": 128, "arp_div": 2, "pad_lp": 3200, "arp_vol": 0.30, "bass_vol": 0.55, "pad_vol": 0.22, "tremolo": 0.25},
    "calm":       {"bpm": 80,  "arp_div": 1, "pad_lp": 1800, "arp_vol": 0.22, "bass_vol": 0.40, "pad_vol": 0.30, "tremolo": 0.45},
    "cinematic":  {"bpm": 92,  "arp_div": 1, "pad_lp": 2400, "arp_vol": 0.25, "bass_vol": 0.60, "pad_vol": 0.26, "tremolo": 0.35},
    "corporate":  {"bpm": 112, "arp_div": 2, "pad_lp": 2800, "arp_vol": 0.28, "bass_vol": 0.50, "pad_vol": 0.24, "tremolo": 0.20},
}

ROOTS = [45, 43, 47, 41, 48, 44]  # A2, G2, B2, F2, C3, G#2 — variety per track


def triad(root_midi: int, quality: str):
    third = 4 if quality == "maj" else 3
    return [root_midi, root_midi + third, root_midi + 7]


def build_track(category: str, idx: int, seed: int) -> dict:
    rng = random.Random(seed)
    params = CATEGORY_PARAMS[category]
    bpm = params["bpm"] + rng.choice([-4, 0, 0, 4])
    root = ROOTS[idx % len(ROOTS)]
    prog = PROGRESSIONS[category][idx % len(PROGRESSIONS[category])]

    inputs = []      # list of (ffmpeg lavfi source, volume, delay_ms)
    # --- pad + bass: one chord per 7.5s slot
    for ci, (offset, qual) in enumerate(prog):
        start_ms = int(ci * CHORD_SEC * 1000)
        for tone in triad(root + offset, qual):
            inputs.append((
                f"sine=frequency={midi_to_freq(tone):.2f}:duration={CHORD_SEC}:beep_factor=0.02",
                params["pad_vol"], start_ms, "pad",
            ))
        # sub bass on chord root, one octave down
        inputs.append((
            f"sine=frequency={midi_to_freq(root + offset - 12):.2f}:duration={CHORD_SEC}:beep_factor=0.35",
            params["bass_vol"], start_ms, "bass",
        ))
    # --- arpeggio across the whole track
    step = 60.0 / bpm / params["arp_div"]
    t = 0.0
    arp_tones_pool = []
    for offset, qual in prog:
        arp_tones_pool.append([n + 12 for n in triad(root + offset, qual)] + [root + offset + 24])
    note_i = 0
    while t < TRACK_SEC - 0.05:
        ci = min(int(t / CHORD_SEC), 3)
        pool = arp_tones_pool[ci]
        tone = pool[note_i % len(pool)]
        # gentle human-ish variation every 8th note
        if rng.random() < 0.12:
            tone += rng.choice([0, 0, 12])
        inputs.append((
            f"sine=frequency={midi_to_freq(tone):.2f}:duration={step * 1.6:.3f}:beep_factor=4",
            params["arp_vol"], int(t * 1000), "arp",
        ))
        t += step
        note_i += 1

    return {
        "category": category, "index": idx, "bpm": bpm,
        "root_midi": root, "inputs": inputs, "params": params,
    }


def render_track(track: dict, out_path: str):
    params = track["params"]
    cmd = ["ffmpeg", "-y", "-v", "error"]
    for src, _vol, _delay, _kind in track["inputs"]:
        cmd += ["-f", "lavfi", "-i", src]

    filt = []
    for i, (_src, vol, delay, kind) in enumerate(track["inputs"]):
        filt.append(
            f"[{i}:a]aresample=44100,aformat=channel_layouts=stereo,"
            f"volume={vol},adelay={delay}|{delay}[s{i}]"
        )
    labels = "".join(f"[s{i}]" for i in range(len(track["inputs"])))
    # Separate buses so pad/arp/bass can be shaped independently.
    # NOTE: we mixed all inputs together above; split shaping happens by
    # re-using per-kind amix chains:
    pad_labels = "".join(f"[s{i}]" for i, x in enumerate(track["inputs"]) if x[3] == "pad")
    arp_labels = "".join(f"[s{i}]" for i, x in enumerate(track["inputs"]) if x[3] == "arp")
    bass_labels = "".join(f"[s{i}]" for i, x in enumerate(track["inputs"]) if x[3] == "bass")
    n_pad = sum(1 for x in track["inputs"] if x[3] == "pad")
    n_arp = sum(1 for x in track["inputs"] if x[3] == "arp")
    n_bass = sum(1 for x in track["inputs"] if x[3] == "bass")
    filt.append(
        f"{pad_labels}amix=inputs={n_pad}:normalize=0,"
        f"tremolo=f=0.4:d={params['tremolo']},lowpass=f={params['pad_lp']}[pad]"
    )
    filt.append(
        f"{arp_labels}amix=inputs={n_arp}:normalize=0,highpass=f=700[arp]"
    )
    filt.append(
        f"{bass_labels}amix=inputs={n_bass}:normalize=0,lowpass=f=320[bass]"
    )
    filt.append(
        "[pad][arp][bass]amix=inputs=3:normalize=0,"
        "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=44100,aformat=channel_layouts=stereo[out]"
    )
    cmd += ["-filter_complex", ";".join(filt),
            "-map", "[out]", "-t", str(TRACK_SEC),
            "-c:a", "libmp3lame", "-b:a", "160k", "-ar", "44100", out_path]
    subprocess.run(cmd, check=True)


def main():
    os.makedirs(ASSETS_DIR, exist_ok=True)
    os.makedirs(SEED_DIR, exist_ok=True)
    manifest = []
    n = 0
    for category in ("energetic", "calm", "cinematic", "corporate"):
        for i in range(6):
            n += 1
            name = f"{category}_{i + 1:02d}.mp3"
            out = os.path.join(ASSETS_DIR, name)
            track = build_track(category, i, seed=1000 + n)
            print(f"[{n:2d}/24] rendering {name} (bpm={track['bpm']})...", flush=True)
            render_track(track, out)
            shutil.copy2(out, os.path.join(SEED_DIR, name))
            manifest.append({
                "file": name, "category": category, "bpm": track["bpm"],
                "root_midi": track["root_midi"], "duration_sec": TRACK_SEC,
                "license": "original procedural composition — bundled royalty-free",
            })
    with open(os.path.join(ASSETS_DIR, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    shutil.copy2(os.path.join(ASSETS_DIR, "manifest.json"),
                 os.path.join(SEED_DIR, "manifest.json"))
    print(f"Done: 24 tracks in {ASSETS_DIR} (+ seed copy in {SEED_DIR})")


if __name__ == "__main__":
    sys.exit(main())
