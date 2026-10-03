# CutPilot AI — Auto Video-Editing Studio

Upload raw footage → AI analyzes it deeply (speech, silences, fillers, scenes,
energy, hook, keywords) → an edit plan is generated like a human editor would
cut it → motion graphics, kinetic captions, B-roll and auto-ducked music are
applied → you fine-tune in the timeline → one-click Full HD export.

Real upload, real Whisper transcription, real ffmpeg rendering, real MP4 out.
Every button works end-to-end.

## 15-minute setup (local dev)

**Prerequisites:** Python 3.12, Node 24, ffmpeg 8+ (`ffmpeg -version`).

```bash
# 1. backend
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8000        # API at http://localhost:8000

# 2. frontend (new terminal)
cd frontend
npm install
npm run dev                                        # UI at http://localhost:3000

# 3. seed data (demo users + demo project, explorable instantly, no upload needed)
.venv/bin/python seed.py
# Uses backend/seed_data/demo_analysis.json + demo_edit_plan.json when present
# (60s talking-head sample analysis + edit plan), else builds demo media with
# ffmpeg and runs the real pipeline.
```

Faster first run: set `WHISPER_MODEL=tiny` in your environment — transcription
of a 1-minute clip then takes ~1–2 min on CPU instead of ~5.

**Docker (one command, needs Docker installed):**

```bash
cp .env.example .env   # fill in secrets as needed
docker compose up --build
# web http://localhost:3000 · api http://localhost:8000
```

## Architecture

```
┌─────────────┐      ┌──────────────────────────┐      ┌───────────────┐
│  Next.js 14 │      │  FastAPI (app/main.py)   │      │    Celery     │
│  frontend   │◄────►│  routers: auth, projects │◄────►│  worker       │
│  :3000      │ REST │  pipeline, render,       │queue │  (same image) │
└─────────────┘      │  billing, admin, extras  │      └──────┬────────┘
                     └────────────┬─────────────┘             │
              ┌───────────────────┼───────────────────────────┼─────────┐
              ▼                   ▼                           ▼         ▼
        ┌──────────┐        ┌────────────┐              ┌──────────┐ ┌────────┐
        │PostgreSQL│        │   storage/ │              │  Redis   │ │ffmpeg  │
        │  :5432   │        │ uploads/   │              │  :6379   │ │ 8.1.2  │
        │projects, │        │ projects/  │              │ broker + │ │renders │
        │users,    │        │ renders/   │              │ progress │ │EVERY-  │
        │plans...  │        │ assets/    │              │ pub/sub  │ │THING   │
        └──────────┘        └────────────┘              └──────────┘ └────────┘
```

No Redis/Postgres locally? The backend auto-falls back: SQLite
(`./cutpilot.db`) + in-process `ThreadPoolExecutor` job queue, so
`uvicorn app.main:app` alone runs the whole pipeline.

### Pipeline explainer — the 9 stages

| # | Stage | What happens | Code |
|---|-------|--------------|------|
| A | Upload & ingest | drag-drop/file/URL import; `ffprobe` (duration, res, fps, codec); orientation detect; waveform + thumbnail strip | `app/services/ingest.py` |
| B | Deep analysis | faster-whisper word timestamps → filler/silence/scene/energy/hook/keyword/audio-QC/summary stages → `analysis.json` | `app/services/analysis_pipeline.py` + `stages/` |
| C | Edit plan | rules-first planner: smart cuts (word-boundary snapped, 80–120 ms padding), pacing, B-roll/graphics/caption/music plans, every decision logged with a `reason` | `app/services/planner.py` |
| D | Motion graphics | kinetic typography (7 drawtext styles), lower thirds, callouts, stat popups, quote cards, progress bar, subscribe bug — see "ffmpeg-native" note below | `app/services/kinetic.py`, `graphics.py` |
| E | B-roll | Pexels/Pixabay keyword matching (key-pluggable) + user uploads + AI prompt suggestions; muted/ducked under voice | `app/services/broll.py` |
| F | Captions | word-level karaoke burn-in, 10+ styles, 4–5 words/line for shorts | `app/services/captions.py` |
| G | Audio post | `afftdn` denoise → `-14 LUFS` loudnorm → sidechain ducking of BGM under voice | `app/services/audio_post.py` |
| H | Timeline editor | multi-track editor UI, trim/split/ripple, caption word edit, undo/redo, "Re-run AI" | `frontend/app/project/[id]/edit` |
| I | Render & export | render queue w/ progress, presets 1080p/4K/720p/9:16/1:1, `{project}_{preset}_{date}.mp4`, download + share link + YouTube stub | `app/services/render_pipeline.py`, `app/routers/render.py` |

### Architecture decision: ffmpeg-native motion graphics (no browser farm)

The spec allowed headless-Chromium/Remotion rendering. We deliberately chose
**ffmpeg-native** instead:

- **Kinetic typography** is generated as `drawtext` filter graphs with
  per-frame expressions (`fontsize='…'`, `x='…'`, `y='…'`, `alpha='…'`,
  `enable='between(t,T0,T1)'`) — 7 styles (scale-pop, slide-up, slide-left,
  typewriter, bounce, glow-pulse, zoom-out). No DOM, no fonts-in-browser pain.
- **Cards & overlays** (lower thirds, callouts, stat popups, quote cards,
  progress bar, subscribe bug, intro/outro) are pre-rendered to transparent
  PNGs with PIL, then composited with `overlay=…:enable='between(t,…)'`.
- Why: a render worker needs only the `ffmpeg` binary — no Chromium, no
  Playwright, no Node SSR farm, no GPU. Renders are deterministic,
  frame-accurate, and the whole pipeline runs on one small VM. The tradeoff
  (no arbitrary CSS/JS animation) is acceptable: every graphic in the product
  is data-driven from transcript words + timestamps anyway.

## API docs (route table)

Base: `http://localhost:8000/api/v1`. Auth: `Authorization: Bearer <jwt>`.

| Method & path | Description |
|---|---|
| `POST /auth/signup` | `{email, password, name}` → tokens (5 free credits) |
| `POST /auth/login` | form `username`/`password` → tokens |
| `POST /auth/refresh` · `GET /auth/me` | session |
| `POST /auth/forgot-password` · `POST /auth/reset-password` | reset flow |
| `GET /projects` · `POST /projects` | list / create `{name}` |
| `GET/PATCH/DELETE /projects/{id}` | project CRUD |
| `POST /projects/{id}/upload` | multipart `file` (mp4/mov/webm/mkv/mp3/wav) |
| `POST /projects/{id}/import-url` | YouTube/Drive URL import |
| `GET /projects/{id}/source` · `/thumbnail` | media serving |
| `POST /projects/{id}/analyze` | queue deep analysis |
| `GET /projects/{id}/status` | `{status, progress}` — poll this |
| `GET /projects/{id}/analysis` | the `analysis.json` |
| `POST /projects/{id}/plan` | `{style, options}` (e.g. `{"pacing":"energetic"}`) |
| `GET /projects/{id}/plan` · `PUT /projects/{id}/plan` | latest plan / save edited plan |
| `GET /projects/{id}/plan/versions` · `POST .../restore/{v}` | version history |
| `GET /projects/{id}/shorts` · `POST .../shorts/extract` | shorts extractor |
| `GET /projects/{id}/chapters` | YouTube chapters |
| `GET/POST /projects/{id}/thumbnails[/generate]` | thumbnail generator |
| `POST /projects/{id}/render` | `{preset: 1080p\|4k\|720p\|9:16\|1:1}` (credits deducted) |
| `GET /renders` · `GET /renders/{rid}` | render jobs |
| `GET /renders/{rid}/download` | the MP4 |
| `POST /projects/{id}/publish/youtube` | YouTube publish (stub w/ real code path) |
| `GET /templates` | 25 style templates |
| `GET/PUT /brand-kit` | logo, colors, fonts |
| `GET /billing/plans` · `POST /billing/checkout` | Stripe test-mode |
| `GET /admin/health` · `/admin/users` · `/admin/jobs` · `/admin/workers` | admin |
| `POST /teams` · `GET /teams` · `GET/PATCH/DELETE /teams/{id}` | team workspaces |
| `POST /teams/{id}/invite` | `{email, role}` → join token |
| `POST /teams/invites/{token}/accept` | join a team |
| `GET/PATCH /teams/{id}/members[/{uid}]` | member list / role change |
| `GET/POST /projects/{id}/comments` | timestamp-pinned comments |
| `POST /batch` · `GET /batch/{id}` | batch processing |
| `POST /projects/{id}/voiceover` | `{script, voice}` → TTS (stub w/o provider) |
| `GET /projects/{id}/metadata?platform=` | title/desc/hashtags/chapters per platform |
| `GET /healthz` | public liveness |

## Ports

| Service | Port |
|---|---|
| frontend (Next.js) | 3000 |
| api (FastAPI) | 8000 |
| worker (Celery) | — (no port; broker only) |
| postgres | 5432 |
| redis | 6379 |

## Demo logins

Seed script creates (see `backend/seed_data/`):

| Email | Password | Role | Notes |
|---|---|---|---|
| `demo@cutpilot.ai` | `DemoPass123!` | user | demo project pre-loaded (36s narrated sample: real Whisper analysis + edit plan) |
| `admin@cutpilot.ai` | `AdminPass123!` | admin | `/admin` access |

Created by `backend/seed.py` (step 3 above).

## BGM library — original by construction

`assets/music/` ships **24 royalty-free tracks** (energetic/calm/cinematic/
corporate × 6, 30 s, 44.1 kHz, −16 LUFS). They are **synthesized from scratch**
by `scripts/gen_bgm.py` — layered sine oscillators (chord pads, arpeggios,
sub bass), no samples, no third-party audio — so they are original compositions
and safe to bundle. A `manifest.json` maps track → category/BPM for the music
planner. Re-run the generator anytime to make more.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `pip install` slow / whisper download slow | `WHISPER_MODEL=tiny` (env) — 75 MB model, fine on CPU |
| Analysis stuck at 0% | check `/tmp/e2e_uvicorn.log`-style server log; whisper downloads on first run |
| `402 Insufficient credits` on render | new signups get 5 credits; 1 credit = 1 min of video |
| Port 8000 busy | `uvicorn app.main:app --port 8123` (e2e uses 8123) |
| Redis/Postgres not running | backend auto-falls back to SQLite + in-process queue — no action needed |
| Render 404 on download | poll `GET /renders/{id}` until `"status":"done"` first |
| Frontend can't reach API | `NEXT_PUBLIC_API_URL` must point at the API (default `http://localhost:8000`) |
| Vision/LLM/B-roll empty | those stages are key-pluggable; without keys the pipeline continues audio-only and notes it in `analysis.json` (`vision_status`) |

## End-to-end test

```bash
./scripts/e2e_test.sh
```

Generates a 45 s test clip (TTS narration with real pauses + "um"/"uh"
fillers), boots the API on :8123, signs up, uploads, analyzes, plans
(`pacing: energetic`), runs the no-mid-word-cut validator, renders 1080p,
downloads and `ffprobe`-checks the MP4 (1920×1080, h264, audio present).
Exits 0 only if every step passes.
