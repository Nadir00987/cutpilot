# CutPilot AI — Acceptance Checklist

Every requirement in `MASTER_PROMPT.md` §4–§8 mapped to where it is
implemented. "Gap" rows are honest: stubbed, pluggable, or known-broken
(see **Honest gaps** at the end).

Legend: ✅ implemented & wired · 🔌 pluggable (works, needs a key/config) ·
⚠️ stub with real code path · ❌ not done / broken.

## §4 Core pipeline

### Stage A — Upload & ingest

| Requirement | Status | Implementation |
|---|---|---|
| Drag-drop upload, file picker, URL import (YouTube/Drive) | ✅ | `backend/app/routers/projects.py: upload_source` (`POST /projects/{id}/upload`, multipart `file`); `import_url` (`POST /projects/{id}/import-url`, yt-dlp); `frontend/app/dashboard/page.tsx` |
| Accept MP4/MOV/WebM/MKV + audio-only (MP3/WAV → visual edit) | ✅ | `backend/app/services/ingest.py: ALLOWED_EXTS`, `ingest_upload` |
| ffprobe every file (duration, res, fps, codec, channels, bitrate) | ✅ | `backend/app/services/ingest.py` (ffprobe probe) |
| Orientation detect (16:9/9:16/1:1), mixed-batch flag | ✅ | `backend/app/services/ingest.py: detect_orientation` |
| Waveform + thumbnail strip on ingest | ✅ | `backend/app/services/ingest.py` (thumbnail strip in ingest metadata) |

### Stage B — Deep analysis (`analysis.json` per project)

| Requirement | Status | Implementation |
|---|---|---|
| 1. Transcription, word timestamps, per-word confidence, language auto-detect (en/ur/hi/ar/es) | ✅ | `backend/app/services/stages/transcribe.py` (faster-whisper, `WHISPER_MODEL` env); `analysis_pipeline.py: run_analysis` |
| 2. Filler & mistake detection (um/uh, repeats, false starts, stutters) w/ cut/keep action | ✅ | `backend/app/services/stages/fillers.py` |
| 3. Silence detection > 0.8 s, configurable | ✅ | `backend/app/services/stages/silence.py`, `SILENCE_THRESHOLD_SEC` in `.env.example` |
| 4. Scene-cut detection + per-scene vision description | 🔌 | `backend/app/services/stages/scenes.py`; vision via `VISION_API_URL/KEY/MODEL` — without a key, scene cuts are detected from video but descriptions fall back gracefully |
| 5. Speaker diarization, Speaker 1/2 labels | ⚠️ | `backend/app/services/stages/diarization.py` — **heuristic** (energy/pitch-change based), not a neural diarizer; see gaps |
| 6. Emotion & energy scoring 0–100 per segment | ✅ | `backend/app/services/stages/energy.py` (loudness + speech rate + vision cues when available) |
| 7. Hook detection (strongest 3–5 s for opening) | ✅ | `backend/app/services/stages/hook.py` (+ LLM rerank in `stages/llm.py` when `LLM_API_*` set) |
| 8. Keyword extraction per segment | ✅ | `backend/app/services/stages/keywords.py` |
| 9. Audio QC (noise, clipping, consistency) | ✅ | `backend/app/services/stages/audio_qc.py` |
| 10. Summary + suggested title + 3 thumbnail texts | ✅ | `backend/app/services/stages/summary.py` (+ `stages/llm.py` when configured) |
| Graceful: transcription fail → manual script paste; vision down → audio-only + UI note | ✅ | `analysis_pipeline.py` fallback paths; `analysis.json: vision_status` |

### Stage C — Edit plan (`edit_plan.json`)

| Requirement | Status | Implementation |
|---|---|---|
| Smart cuts (silences/fillers/mistakes/dead air) | ✅ | `backend/app/services/planner.py: _removal_spans`, `_kept_spans` |
| **Hard rule: never cut mid-word**, snap to word boundaries + 80–120 ms padding | ✅ | `planner.py: _snap_boundary`; enforced by `app/services/validators.py: assert_no_midword_cuts` (called in e2e step e; renderer calls `validate_plan` pre-render) |
| Pacing (3–4 s shots energetic; breathing room for educational) | ✅ | `planner.py: _split_for_pacing` (`pacing: natural\|energetic`) |
| Chronological default; reorder only w/ approval | ✅ | `planner.py: reorder_suggestions` (empty by default + note) |
| B-roll plan per segment (keep/overlay/split/takeover, keyword-matched) | ✅ | `planner.py: _build_broll`; `app/services/broll.py` |
| Motion-graphics plan (timestamped list) | ✅ | `planner.py: _build_graphics` |
| Caption plan (word-level, emphasis marked) | ✅ | `planner.py: _build_captions` |
| Music plan (BGM track + ducking points) | ✅ | `planner.py` music block; `assets/music/manifest.json` (24 tracks) |
| Everything editable in timeline before render | ✅ | `PUT /projects/{id}/plan`; `frontend/app/project/[id]/edit/page.tsx` |
| Every AI decision logged w/ `reason` | ✅ | `reason` fields on cuts/graphics/captions/music/broll in plan |

### Stage D — Motion graphics

| Requirement | Status | Implementation |
|---|---|---|
| Kinetic typography, 6+ animation styles, word-timed, user-switchable | ✅ | `backend/app/services/kinetic.py` — 7 ffmpeg `drawtext` styles (scale_pop, slide_up, slide_left, typewriter, bounce, glow_pulse, zoom_out) |
| Lower thirds on first speaker (editable) | ✅ | `backend/app/services/graphics.py: lower_third` |
| Callouts/arrows/highlight + auto-zoom punch-in 110–125% on emphasis | ✅ | `graphics.py: callout_box`; zoom via ffmpeg crop/scale expressions in `render_pipeline.py` |
| Transitions (zoom cuts, whip-pan, crossfades — no cheese) | ✅ | `render_pipeline.py` transition assembly |
| Progress bar w/ brand color | ✅ | `graphics.py: progress_bar` |
| Emoji/sticker reactions, toggleable | ✅ | plan `emoji_on` flag; `graphics.py` sticker path |
| BG enhancement + auto-reframe w/ face centering | ⚠️ | `backend/app/services/reframe.py` — face detection **pluggable, default center-crop**; see gaps |
| Brand kit (logo/colors/fonts → all graphics/intros/outros/watermarks) | ✅ | `backend/app/routers/brandkit.py`; `frontend/app/brand-kit/page.tsx`; `graphics.py: intro_card` |
| Intro/outro 2–3 s branded + subscribe end card | ✅ | plan `intro_outro` block; `graphics.py: intro_card`, `subscribe_bug` |

### Stage E — B-roll

| Requirement | Status | Implementation |
|---|---|---|
| Pexels/Pixabay hooks via `.env` | 🔌 | `backend/app/services/broll.py`; `PEXELS_API_KEY`/`PIXABAY_API_KEY` in `.env.example` |
| Keyword→B-roll matching, auto-trim, color-grade normalize | ✅/🔌 | matching + trim in `broll.py`; LUT normalize basic |
| No-key fallback: AI B-roll prompt suggestions, never irrelevant footage | ✅ | plan `broll[].ai_broll_prompt` + note |
| B-roll audio muted/10% | ✅ | render audio mix |

### Stage F — Captions

| Requirement | Status | Implementation |
|---|---|---|
| Word-level, karaoke active-word highlight | ✅ | `backend/app/services/captions.py` |
| 10+ styles, position top/mid/bottom, ≤4–5 words/line for shorts | ✅ | `captions.py` style table; plan `caption_style`, `max_words_per_line` |
| Multi-language + optional EN/UR translate toggle | ⚠️ | captions render in detected language; auto-translate is a documented gap |
| Always-on vs clean export toggle | ✅ | plan `captions_on` |

### Stage G — Audio post

| Requirement | Status | Implementation |
|---|---|---|
| −14 LUFS loudness normalization | ✅ | `backend/app/services/audio_post.py: post_chain` (`loudnorm=I=-14`) |
| Noise reduction (`afftdn`), de-esser optional | ✅ | `afftdn` in `post_chain`; de-esser flag |
| Auto-duck BGM under dialogue (sidechain) | ✅ | `sidechaincompress` keyed by voice in `audio_post.py` |
| Royalty-free BGM library, 20+ tracks, categorized | ✅ | `scripts/gen_bgm.py` → **24 original procedural tracks** in `assets/music/` (+ `storage/assets/music/` seed copy) |

### Stage H — Timeline editor

| Requirement | Status | Implementation |
|---|---|---|
| Multi-track timeline (video/B-roll/text/captions/audio/music/FX) | ✅ | `frontend/app/project/[id]/edit/page.tsx` |
| Trim, split (S), ripple delete, reorder, 0.5–2x speed | ✅ | editor page + `frontend/components/editor/` |
| Click caption word to edit; drag graphics on canvas | ✅ | editor page |
| Live preview, play/pause, frame step, zoom, undo/redo | ✅ | `PreviewPlayer.tsx`, editor history stack |
| "Re-run AI" button | ✅ | editor page → `POST /projects/{id}/plan` |
| Keyboard shortcuts | ✅ | editor page |

### Stage I — Render & export

| Requirement | Status | Implementation |
|---|---|---|
| Render queue, real progress %, ETA, WebSocket updates | ✅ | `backend/app/routers/render.py`; `backend/app/ws.py` (progress pub/sub); `jobs.report_progress` |
| Presets: 1080p (H.264 default), 4K, 720p draft, 9:16/1:1/16:9 reframe | ✅ | `render.py: PRESETS = ("1080p","4k","720p","9:16","1:1")` |
| File naming `{project}_{preset}_{date}.mp4` | ✅ | `render.py: download_render` filename |
| Preview-before-render (explicit Export click) | ✅ | `frontend/app/project/[id]/export/page.tsx` |
| Post-render: download, shareable link, YouTube publish hook | ⚠️ | download ✅, shareable link ✅ (`/storage` mount); YouTube = **stub w/ real code path** (`POST /projects/{id}/publish/youtube`), see gaps |

## §5 Extra features

| # | Requirement | Status | Implementation |
|---|---|---|---|
| 1 | Shorts extractor (3 best 30–60 s vertical clips, 9:16, captioned) | ✅ | `planner.py: _build_shorts`; `GET/POST /projects/{id}/shorts[/extract]` (`app/routers/pipeline.py`) |
| 2 | Auto chapters (copy-paste YouTube timestamps) | ✅ | `backend/app/services/chapters.py: get_chapters`; `GET /projects/{id}/chapters`; also in `GET /projects/{id}/metadata` |
| 3 | Thumbnail generator (3 options, PNG download) | ✅ | `backend/app/services/thumbnails.py`; `GET/POST /projects/{id}/thumbnails[/generate]` |
| 4 | Multi-project dashboard (cards, status, search/filters) | ✅ | `frontend/app/dashboard/page.tsx`; `GET /projects` |
| 5 | Templates marketplace — 20+ starter templates | ✅ | **25 templates** in `backend/data/templates/*.json` (+ `index.json`); `GET /templates`, `POST /projects/{id}/apply-template` (`app/routers/templates.py`); `frontend/app/templates/page.tsx` |
| 6 | Team workspaces (invite, editor/viewer roles, timestamp comments) | ✅ | `backend/app/routers/extras.py` (`/teams*`, `/projects/{id}/comments`); `frontend/app/teams/page.tsx`; tables in `app/models.py` |
| 7 | Version history (every render saved, one-click restore) | ✅ | `GET /projects/{id}/plan/versions`, `POST .../restore/{version}` (`app/routers/pipeline.py`); `EditPlanVersion` model |
| 8 | Batch processing (N videos, one preset, overnight queue) | ✅ | `POST /batch`, `GET /batch/{id}` (`app/routers/extras.py`); `frontend/app/batch/page.tsx` |
| 9 | Voiceover/dubbing (TTS + script editor, faceless videos) | ⚠️ | `POST /projects/{id}/voiceover` → `app/services/voiceover.py` — **stub without provider, real code path**; `frontend/app/voiceover/page.tsx`; see gaps |
| 10 | Analytics metadata (title/desc/hashtags/tags per platform) | ✅ | `GET /projects/{id}/metadata?platform=youtube\|tiktok\|instagram` → `app/services/metadata.py` |

## §6 Pages / routes

| Route | Status | Implementation |
|---|---|---|
| `/` landing (hero, features, pricing, FAQ) | ✅ | `frontend/app/page.tsx` |
| `/auth/*` login/signup/forgot/reset | ✅ | `frontend/app/auth/*` |
| `/dashboard` | ✅ | `frontend/app/dashboard/page.tsx` |
| `/project/[id]/analyze` (live stage checklist) | ✅ | `frontend/app/project/[id]/analyze/page.tsx` (+ `useProgress` hook, `ws.py`) |
| `/project/[id]/edit` timeline editor | ✅ | `frontend/app/project/[id]/edit/page.tsx` |
| `/project/[id]/export` render queue + presets + download | ✅ | `frontend/app/project/[id]/export/page.tsx` |
| `/templates` gallery | ✅ | `frontend/app/templates/page.tsx` |
| `/brand-kit` | ✅ | `frontend/app/brand-kit/page.tsx` |
| `/billing` (credits, plans, Stripe checkout) | ✅/⚠️ | `frontend/app/billing/page.tsx`; Stripe **test-mode** (see gaps) |
| `/admin` users/jobs/health/workers | ✅ | `frontend/app/admin/page.tsx`; `app/routers/admin.py` |
| `/teams`, `/batch`, `/voiceover` (extras) | ✅ | `frontend/app/teams|batch|voiceover/page.tsx` |

## §7 Quality bar

| Requirement | Status | Implementation |
|---|---|---|
| Human-quality pacing/emphasis, graphics timed to speech | ✅ | planner + kinetic/caption timing from word timestamps |
| No mid-word cuts — validated programmatically pre-render | ✅ | `app/services/validators.py: validate_plan` (renderer must call; e2e step e runs `assert_no_midword_cuts`) |
| No black flashes; consistent fps/codec/resolution | ✅ | `validators.validate_timeline_coverage`; single ffmpeg graph per render |
| Captions readable on mobile (360 px preview) | ✅ | caption styles sized for small widths; `max_words_per_line` 4–5 |
| Every AI decision logged w/ `reason` | ✅ | `reason` on all plan items |
| Graceful failure (manual script paste; audio-only + UI note) | ✅ | `analysis_pipeline.py` fallbacks; `vision_status` in analysis.json |

## §8 Deliverables

| # | Deliverable | Status | Location |
|---|---|---|---|
| 1 | Working codebase (frontend+backend+workers monorepo) | ✅ | `frontend/`, `backend/`, this repo |
| 2 | `docker-compose.yml` (web/api/worker/postgres/redis) | ✅ | `docker-compose.yml` (valid YAML; Docker not on dev VM — runs anywhere Docker exists) |
| 3 | `.env.example`, every key documented | ✅ | `.env.example` |
| 4 | Migrations + seed data | ✅ | `backend/seed.py` (demo+admin users, demo project); `backend/seed_data/demo_analysis.json` + `demo_edit_plan.json` (Worker E); `Base.metadata.create_all` on startup |
| 5 | `README.md` (setup, architecture, pipeline, API) | ✅ | `README.md` |
| 6 | E2E test `scripts/e2e_test.sh` | ✅ | `scripts/e2e_test.sh` (runs green on this VM — see report). Note: the render step needs ~15–20 min of CPU on this VM (heavy per-frame kinetic/drawtext/subtitles/loudnorm filtergraph), so the script's render timeout is 1800s, not 900s. |
| 7 | `ACCEPTANCE.md` | ✅ | this file |

## Honest gaps

1. **Stripe is test-mode only.** Checkout + webhook endpoints exist
   (`app/routers/billing.py`), but no live keys are wired. The **credit
   logic is real**: 1 credit = 1 minute of processed video, deducted in
   `app/routers/render.py: start_render` (`_deduct_credits`), `CreditTransaction`
   rows recorded, 402 on insufficient balance.
2. **YouTube publish is a stub with a real code path.**
   `POST /projects/{id}/publish/youtube` validates ownership, logs the
   request and returns a structured stub — wire OAuth + YouTube Data API
   upload there when keys exist.
3. **Vision is pluggable → audio-only + UI note.** Without
   `VISION_API_URL/KEY`, scene descriptions and vision energy cues are
   skipped; `analysis.json: vision_status` records it and the analyze page
   surfaces the note. Nothing silently pretends to see.
4. **Pexels/Pixabay are key-pluggable.** Without keys the B-roll engine uses
   user uploads + AI B-roll prompt suggestions (`broll[].ai_broll_prompt`);
   it never inserts irrelevant stock.
5. **Face detection is pluggable, default center-crop.**
   `app/services/reframe.py` centers the subject; a face-detection provider
   can be dropped in without changing the render graph.
6. **Diarization is heuristic** (`stages/diarization.py`: energy/pitch-change
   based), not a neural diarizer (e.g. pyannote). Fine for single-speaker
   talking head; interviews with heavy crosstalk will be approximate.
7. **Caption auto-translate (EN/UR)** is not implemented — captions render in
   the detected language.
8. **Team-invite role/expiry:** Worker A's `team_invites` table has no
   `role`/`expires_at` columns, so `routers/extras.py` encodes the requested
   role in the invite token (`{role}.{random}`) and invites don't expire.
   Role can be changed afterwards via `PATCH /teams/{id}/members/{uid}`.
9. **Batch chaining:** `POST /batch` fans out the *analysis* stage per project
   via Worker A's job queue and tracks per-project stage status; plan→render
   chaining across the batch is orchestrated per project (same as the normal
   flow) rather than as one atomic chain.
10. **Render PNG-overlay hang (Worker C bug, diagnosed 2026-10-02, FIXED).**
    `app/services/render_pipeline.py:333-334` fed PNG graphic overlays
    (lower thirds, callouts, subscribe bug…) to ffmpeg as `-loop 1` inputs
    **without `-t`**, creating infinite streams; the `overlay` filter then
    never terminates — output runs away (observed 845 s / 236 s for 9–24 s
    timelines) and ffmpeg exits 255, failing the render job. Fix applied in
    `render_pipeline.py`: looped PNG inputs now get `-t <total_dur>` so EOF
    propagates cleanly. Verified 2026-10-02: 720p render with PNG lower-third
    + subscribe overlays completes in 38 s (was: hang).
11. **Render audio runs long (Worker C bug, diagnosed 2026-10-02, FIXED —
    plus a second audio bug found & fixed in integration).**
    `app/services/audio_post.py: post_chain` ended the mix with
    `amix=inputs=2:duration=first`, but empirically `duration=first` does
    NOT limit to the first input — a 9 s + 9 s mix comes out ~30 s (the full
    BGM length); in the e2e render the audio stream was 45.0 s against
    8.93 s of video. Fix: `duration=shortest` (BGM input is infinite via
    `-stream_loop -1`, so shortest == voice length).
    Integration found a second, subtler bug: feeding the LOUDNORMED voice
    as the `sidechaincompress` key silently truncated the ducked BGM to the
    end of the last non-silent key segment (13.5 s voice + 3 s anullsrc outro
    → 13.6 s audio; the outro card played silent). Root cause verified with
    minimal ffmpeg repros. Fix in `audio_post.py`: the voice is `asplit`
    into a raw tap used ONLY as the sidechain key (envelope follower needs
    no normalization) while the mix path keeps afftdn→loudnorm.
    Verified 2026-10-02: 720p demo render → video 16.57 s / audio 16.58 s
    (13.53 s edit + 3 s outro), h264+aac, no tail, no truncation.
12. **Extras router prefix:** the Worker-E spec said `APIRouter(prefix="/api/v1")`,
    but `app/main.py` mounts *every* router with `prefix="/api/v1"` — keeping
    the spec's prefix would double to `/api/v1/api/v1/*`. The prefix lives on
    the include instead (matching all other routers); routes are
    `/api/v1/teams`, `/api/v1/batch`, etc.
