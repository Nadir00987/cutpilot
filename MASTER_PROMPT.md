# MASTER PROMPT — "CutPilot AI" Auto Video-Editing Studio

## 1. Role & Mission

You are a senior full-stack engineer + professional video editor with 10+ years of editing experience (Premiere Pro, After Effects, DaVinci Resolve, motion graphics, kinetic typography, social-media short-form editing).

Build a **production-ready, fully working web application** called **"CutPilot AI"** — an AI-powered automatic video editing studio.

**Core promise:** A user uploads raw footage or a simple talking-head video. The platform deeply analyzes the entire video (speech, language, visuals, audio), then **automatically edits it like a professional human editor** — cuts, motion graphics, kinetic text, animations, B-roll, captions, transitions, sound design — with a manual timeline for fine-tuning, and one-click Full HD (1080p) export/download.

Do not build a mockup. Build the real thing: real upload, real analysis pipeline, real timeline editor, real ffmpeg rendering, real downloadable MP4 output. Every button must work end-to-end.

---

## 2. Target Users

- YouTubers, coaches, course creators, podcasters (talking-head videos)
- Agencies & freelancers who edit client videos
- Short-form creators (Reels / TikTok / YouTube Shorts)
- Businesses making ads, UGC-style videos, testimonials

---

## 3. Tech Stack (required)

- **Frontend:** Next.js 14+ (App Router) + TypeScript + Tailwind CSS. Dark, premium, Figma-grade UI. Framer Motion for interface animations.
- **Backend:** Python FastAPI (video/AI pipeline) + Node.js (optional render workers). REST API + WebSocket for real-time job progress.
- **Database:** PostgreSQL (projects, users, edit plans, assets). Redis (job queue + caching).
- **Job Queue:** Celery (Python) or BullMQ — long video jobs must run async with progress % over WebSocket.
- **Storage:** Local disk in dev / S3-compatible in production. Organized: `/uploads`, `/renders`, `/assets/broll`, `/assets/music`, `/thumbnails`.
- **Video Engine:** ffmpeg (mandatory). All cutting, concat, overlays, captions burn-in, loudness normalization via ffmpeg.
- **Motion Graphics Engine:** Programmatic compositions — HTML/CSS/JS templates rendered headless (Playwright/Chromium) OR Remotion. Motion graphics must be **data-driven**: transcript words + timestamps feed the animation timeline (kinetic text, lower thirds, callouts).
- **AI Services (pluggable, env-configured):**
  - Speech-to-text with **word-level timestamps**: OpenAI Whisper (local `openai-whisper`) or faster-whisper. Language auto-detect.
  - Vision analysis: frame sampling + vision LLM (configurable endpoint) for scene/object/emotion description.
  - LLM for edit planning: configurable (OpenAI-compatible endpoint). All keys in `.env`, never in code or logs.
- **Auth:** Email + password with JWT, sessions, password reset. Roles: user / admin.
- **Billing:** Credits system (1 credit = 1 minute of processed video). Stripe-ready billing module (can be stubbed with test mode, but the credit deduction logic must be real and working).

---

## 4. Core Pipeline — THE HEART OF THE PRODUCT

This pipeline must be fully automatic. Implement it as discrete, testable stages. **The deep analysis is the differentiator — do not skimp on it.**

### Stage A — Upload & Ingest
- Drag-and-drop upload, file picker, and URL import (YouTube link, Google Drive link).
- Accept MP4, MOV, WebM, MKV, audio-only (MP3/WAV → auto-generate visual edit).
- `ffprobe` every file: duration, resolution, fps, codec, audio channels, bitrate.
- Auto-detect orientation (16:9 / 9:16 / 1:1) and flag mixed-orientation batches.
- Generate waveform + thumbnail strip on ingest.

### Stage B — Deep Video Analysis (backend, automatic)
For every uploaded video, run ALL of the following and store results as structured JSON (`analysis.json` per project):

1. **Transcription:** Full transcript with **word-level timestamps**, per-word confidence. Auto-detect language (support at minimum: English, Urdu, Hindi, Arabic, Spanish). Mark low-confidence words.
2. **Filler & mistake detection:** umm/uhh, repeated words, false starts, long pauses, stutters — each tagged with timestamps and a suggested action (cut / keep), NOT hard-deleted yet.
3. **Silence detection:** silence segments > 0.8s flagged for removal (configurable threshold).
4. **Scene & shot analysis:** scene-cut detection; per-scene description via vision model (what is visible: person talking, screen share, product demo, outdoor, etc.).
5. **Speaker diarization:** detect speaker changes (for interviews/podcasts), label Speaker 1/2.
6. **Emotion & energy scoring:** per-segment energy level (0–100) from audio loudness + speech rate + vision cues. High-energy moments = highlight candidates.
7. **Hook detection:** LLM identifies the strongest 3–5 second hook candidate for the opening.
8. **Keyword extraction:** important nouns/phrases per segment — these drive kinetic text emphasis and B-roll search.
9. **Audio quality check:** background noise level, clipping detection, volume consistency; flag segments needing enhancement.
10. **Content summary:** 3–5 sentence summary + suggested title + 3 thumbnail text options (used later for export metadata).

### Stage C — Automatic Edit Plan (AI Editor Brain)
Feed `analysis.json` into the edit planner (LLM + rules). Output `edit_plan.json`:

- **Smart cuts:** remove silences, fillers, mistakes, dead air. **Hard rule: never cut mid-word** — snap all cut points to word boundaries with 80–120ms padding.
- **Pacing:** target average shot length 3–4s for energetic content; keep educational speech breathing room. Jump-cut talking head on sentence/phrase boundaries.
- **Structure:** reorder only if it improves narrative (keep chronological by default; flag reorder suggestions for user approval).
- **B-roll plan:** for each segment, decide: keep talking head / overlay B-roll / split-screen / full B-roll takeover. B-roll matched by keyword relevance.
- **Motion graphics plan:** timestamped list of every graphic: kinetic headline, lower third, key-point callout, stat popup, progress bar, subscribe animation, zoom/punch-in, emoji reaction, quote card.
- **Caption plan:** word-level caption segments with emphasis words marked.
- **Music plan:** suggest BGM track + ducking points under speech.
- Everything in the plan is **editable** in the timeline before render.

### Stage D — Motion Graphics & Visual Enhancement Engine
Auto-apply, timestamped to the transcript:

1. **Kinetic typography:** key phrases animate in with the spoken word (scale/slide/blur-in, word-by-word highlight like karaoke). Minimum 6 animation styles, user-switchable.
2. **Lower thirds:** auto name/title card on first speaker appearance (editable text).
3. **Callouts & annotations:** arrows, circles, highlight boxes on important moments; auto-zoom (punch-in 110–125%) on emphasis words.
4. **Transitions:** smooth zoom cuts, whip-pan style cuts between segments, subtle crossfades — no cheesy star wipes.
5. **Progress bar:** thin top/bottom progress bar with brand color.
6. **Emoji & sticker reactions:** tasteful, context-matched (celebration, shock, thinking) — toggleable.
7. **Background enhancement:** subtle animated gradient/blur background for vertical crops; auto-reframe keeps the face centered (face detection).
8. **Brand kit:** user uploads logo + picks colors/fonts once → auto-applied to all graphics, intros, outros, watermarks.
9. **Intro/Outro (optional):** 2–3s branded intro + end card with subscribe CTA, auto-generated from brand kit.

### Stage E — B-roll Engine
- Built-in stock library hooks (Pexels / Pixabay API keys via `.env`) + user-uploaded B-roll folder.
- Keyword → B-roll matching from Stage B; auto-download, auto-trim to segment length, auto color-grade to match main footage (basic LUT normalization).
- Fallback: if no good match, generate AI B-roll prompt suggestions (text-to-video provider pluggable) — do NOT silently insert irrelevant footage.
- B-roll ducking: main audio stays dominant; B-roll audio muted or at 10%.

### Stage F — Captions (automatic, styled)
- Word-level captions synced to speech, karaoke-style active-word highlight.
- 10+ caption styles (Hormozi-style big bold, minimal, karaoke, outline, etc.), position top/middle/bottom, auto line-breaking (max 4–5 words per line for shorts).
- Multi-language: captions in detected language; optional auto-translate to English/Urdu.
- Toggle: always-on / clean video export without captions.

### Stage G — Audio Post-Production (automatic)
- Loudness normalization to −14 LUFS (YouTube/social standard).
- Background noise reduction (ffmpeg afftdn), de-esser optional.
- Auto-duck BGM under dialogue (sidechain-style volume automation).
- Royalty-free BGM library included (bundle 20+ tracks, categorized: energetic, calm, cinematic, corporate) + user upload.

### Stage H — Timeline Editor (manual control)
After auto-edit, the user lands in a full timeline editor:

- Multi-track timeline: Video (main), B-roll, Text/Graphics, Captions, Audio (voice), Music, Effects.
- Drag to trim, split (S key), ripple delete, drag-and-drop reorder, per-clip speed (0.5x–2x).
- Click any caption word to edit text; drag graphics on the preview canvas to reposition.
- Live preview player with play/pause, frame step, zoomable timeline, undo/redo (full history stack).
- **"Re-run AI" button:** re-generate the edit plan with different style settings without re-uploading.
- Keyboard shortcuts for common actions (space, S, C, arrows).

### Stage I — Render & Export
- Render queue with real progress bar (frame-accurate %), ETA, and WebSocket updates.
- **Export presets:** 1080p Full HD MP4 (H.264, default), 4K MP4, 720p draft, 9:16 / 1:1 / 16:9 auto-reframe versions from one project.
- File naming: `{project}_{preset}_{date}.mp4`.
- **Preview-before-render rule:** user must see the timeline/preview; render only on explicit "Export" click.
- Post-render: download button, shareable link, direct publish hooks (YouTube API pluggable — stub the UI, keep the code path real).

---

## 5. Extra Features (add all of these)

1. **Shorts extractor:** one click → AI picks the 3 best 30–60s vertical clips, auto-reframed 9:16 with captions, ready to post.
2. **Auto chapters:** YouTube chapter timestamps generated from segment topics, copy-paste ready.
3. **Thumbnail generator:** 3 AI-designed thumbnail options (title text + frame grab + style), downloadable PNG.
4. **Multi-project dashboard:** project cards with thumbnail, duration, status (analyzing / ready / rendering / done), search & filters.
5. **Templates marketplace (in-app):** 20+ starter style templates (Vlog, Podcast, Course, Ad/UGC, Testimonial, Fitness) — one-click apply re-skins all graphics.
6. **Team workspaces:** invite members, roles (editor/viewer), comments pinned to timeline timestamps.
7. **Version history:** every render saved; restore any previous edit plan with one click.
8. **Batch processing:** upload 10 videos → same style preset applied to all, overnight queue.
9. **Voiceover / dubbing:** optional AI voiceover track (TTS) + script editor for faceless videos.
10. **Analytics-ready metadata:** auto title, description, hashtags, tags per platform (YouTube/TikTok/Instagram).

---

## 6. Pages / Routes

- `/` — Landing page (hero with live demo video, features, pricing, FAQ). Premium dark UI, animated.
- `/auth/*` — login, signup, forgot password.
- `/dashboard` — projects grid, upload button, credits balance, recent renders.
- `/project/[id]/analyze` — analysis progress view (live stage checklist: transcription → vision → planning…).
- `/project/[id]/edit` — the timeline editor (the flagship page).
- `/project/[id]/export` — render queue + export presets + download/share.
- `/templates` — style template gallery.
- `/brand-kit` — logo, colors, fonts, intro/outro settings.
- `/billing` — credits, plans, Stripe checkout.
- `/admin` — users, jobs, system health, API key management, render worker status.

---

## 7. Quality Bar (non-negotiable)

- **Editing quality is the product.** The auto-edit must genuinely look like a skilled human editor's work: pacing, emphasis, graphics timed to the spoken word — not random overlays.
- No mid-word cuts. Ever. Validate programmatically before render.
- No black flashes between segments; consistent fps/codec/resolution across the whole timeline.
- Captions readable on mobile: test with 360px-wide preview.
- Every AI decision logged in `edit_plan.json` with a reason field — the user can audit why each cut/graphic was added.
- Graceful failure: if transcription fails, allow manual script paste and continue; if vision API is down, continue with audio-only analysis and note it in the UI.

---

## 8. Deliverables

1. Complete working codebase (frontend + backend + workers) in a clean monorepo.
2. `docker-compose.yml` — one command to run everything (web, api, worker, postgres, redis).
3. `.env.example` with every key documented.
4. Database migrations + seed data (demo project with sample analysis so the editor UI is explorable instantly).
5. `README.md` — setup (under 15 min), architecture diagram, pipeline explanation, API docs.
6. Sample end-to-end test: upload a test clip → analysis → edit → render → download, scripted as `scripts/e2e_test.sh`.
7. Acceptance checklist in `ACCEPTANCE.md` mapping each requirement above to where it's implemented.

---

## 9. Build Order

1. Scaffold monorepo + docker-compose + auth + dashboard shell.
2. Upload + ingest + ffprobe pipeline.
3. Transcription (Whisper) + analysis JSON.
4. Edit planner (rules first, LLM second) + `edit_plan.json`.
5. Timeline editor UI (read-only preview of plan first, then full editing).
6. Motion graphics renderer (one kinetic style → then the library).
7. Captions + B-roll + audio post.
8. Render queue + export presets + download.
9. Brand kit, templates, shorts extractor, thumbnails, chapters.
10. Billing/credits, admin, landing page polish, e2e test.

Build it stage by stage. After each stage, verify it works before moving on. When done, walk me through the whole product: upload → analysis → auto-edit → timeline → export, with screenshots or a screen recording of the real working app.
