"use client";
import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import { useState } from "react";
import { Navbar, Footer } from "@/components/Navbar";
import { Button, Card } from "@/components/ui";
import { useAuth } from "@/lib/auth";

const ease = [0.22, 1, 0.36, 1] as const;

function Stagger({
  children,
  className,
  delay = 0,
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduce ? { opacity: 1 } : { opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.45, ease: [...ease], delay }}
    >
      {children}
    </motion.div>
  );
}

const FEATURES = [
  {
    title: "Deep AI analysis",
    body: "Word-level transcription, filler & silence detection, scene understanding, speaker diarization, energy scoring, hook detection — 11 stages before a single cut is made.",
    icon: "M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z",
  },
  {
    title: "Edits like a human",
    body: "Smart jump cuts snapped to word boundaries, pacing tuned to your content, B-roll matched by keyword relevance, and every decision logged with a reason you can audit.",
    icon: "M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664zM21 12a9 9 0 11-18 0 9 9 0 0118 0z",
  },
  {
    title: "Kinetic motion graphics",
    body: "Word-synced kinetic typography, lower thirds, callouts, stat popups, progress bars and punch-ins — 6+ animation styles, skinned automatically with your brand kit.",
    icon: "M7 4v16M17 4v16M3 8h4M17 8h4M3 12h18M3 16h4M17 16h4M4 20h16a1 1 0 001-1V5a1 1 0 00-1-1H4a1 1 0 00-1 1v14a1 1 0 001 1z",
  },
  {
    title: "Karaoke captions",
    body: "Word-level captions with active-word highlight in 10+ styles — Hormozi bold, minimal, karaoke, outline. Multi-language, auto line-breaking for mobile.",
    icon: "M8 10h.01M12 12h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z",
  },
  {
    title: "One-click export",
    body: "1080p Full HD default, plus 4K, 720p draft, and auto-reframed 9:16 / 1:1 from one project. Frame-accurate render queue with live progress and ETA.",
    icon: "M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4",
  },
  {
    title: "Shorts, chapters, thumbnails",
    body: "AI picks your 3 best 30–60s vertical clips, generates YouTube chapters, and designs 3 thumbnail options — all from the same analysis.",
    icon: "M13 10V3L4 14h7v7l9-11h-7z",
  },
];

const PIPELINE = [
  { stage: "Upload & ingest", detail: "Drag-drop or URL import. ffprobe scans codec, fps, resolution, orientation." },
  { stage: "Deep analysis", detail: "11 AI stages: transcription → filler/silence → scenes → diarization → energy → hook → keywords → audio QC → summary." },
  { stage: "Edit planning", detail: "LLM + rules build edit_plan.json. Smart cuts never land mid-word — snapped to word boundaries with padding." },
  { stage: "Motion graphics", detail: "Kinetic text, lower thirds, callouts, progress bars — timestamped to the spoken word." },
  { stage: "Captions & audio", detail: "Karaoke captions in 10+ styles. Loudness to −14 LUFS, noise reduction, BGM ducking." },
  { stage: "Timeline & export", detail: "Fine-tune in the 7-track timeline editor, then one-click 1080p / 4K / 9:16 render." },
];

const PLANS = [
  {
    name: "Starter",
    price: "$19",
    credits: "120 credits",
    blurb: "For testing the waters",
    features: ["120 min of processing", "1080p exports", "5 caption styles", "1 brand kit", "Community support"],
  },
  {
    name: "Creator",
    price: "$49",
    credits: "400 credits",
    blurb: "For weekly creators",
    features: ["400 min of processing", "4K exports", "All caption styles", "Shorts extractor", "3 brand kits", "Priority queue"],
    popular: true,
  },
  {
    name: "Studio",
    price: "$149",
    credits: "1,500 credits",
    blurb: "For teams & agencies",
    features: ["1,500 min of processing", "Everything in Creator", "Team workspaces", "Batch processing", "API access", "Dedicated support"],
  },
];

const FAQS = [
  {
    q: "How does the auto-edit actually work?",
    a: "CutPilot transcribes your footage with word-level timestamps, detects fillers/silences/mistakes, scores energy per segment, then builds an edit plan — cuts, B-roll, kinetic text, captions — all timed to the spoken word. You review everything in a 7-track timeline before rendering.",
  },
  {
    q: "Will it cut mid-word?",
    a: "Never. Every cut point is snapped to word boundaries with 80–120ms padding, validated programmatically before render. Black flashes and codec mismatches are rejected too.",
  },
  {
    q: "What does 1 credit get me?",
    a: "1 credit = 1 minute of processed video. Analysis, planning and rendering a 10-minute video costs 10 credits. Failed jobs never consume credits.",
  },
  {
    q: "Can I edit the AI's decisions?",
    a: "Yes — that's the point. The timeline editor gives you full control: trim, split, ripple delete, reorder, per-clip speed, inline caption editing, draggable graphics, undo/redo, and one-click 'Re-run AI' with different style settings.",
  },
  {
    q: "What export formats are supported?",
    a: "1080p Full HD MP4 (H.264) by default, 4K, 720p draft, and auto-reframed 9:16 vertical and 1:1 square versions from a single project.",
  },
];

function FaqItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-[var(--border)]">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full cursor-pointer items-center justify-between py-5 text-left"
      >
        <span className="font-display text-base font-semibold">{q}</span>
        <motion.span animate={{ rotate: open ? 45 : 0 }} className="text-[var(--accent)] text-2xl leading-none">+</motion.span>
      </button>
      {open && (
        <motion.p
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="overflow-hidden pb-5 text-sm leading-relaxed text-[var(--muted-fg)]"
        >
          {a}
        </motion.p>
      )}
    </div>
  );
}

export default function Landing() {
  const { user } = useAuth();
  const reduce = useReducedMotion();

  return (
    <div className="min-h-screen bg-black text-[var(--fg)]">
      <Navbar />

      {/* HERO */}
      <section className="relative overflow-hidden">
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(ellipse 80% 60% at 50% -10%, rgba(225,29,72,0.22), transparent 60%), radial-gradient(ellipse 60% 50% at 80% 110%, rgba(99,102,241,0.14), transparent 60%)",
          }}
        />
        <div className="relative mx-auto max-w-7xl px-4 pb-24 pt-20 text-center sm:px-6 sm:pt-28">
          <motion.div
            initial={reduce ? { opacity: 1 } : { opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [...ease] }}
            className="mb-6 inline-flex items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--card)] px-4 py-1.5 text-sm text-[var(--muted-fg)]"
          >
            <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--accent)]" />
            AI auto video-editing studio — now in open beta
          </motion.div>
          <motion.h1
            initial={reduce ? { opacity: 1 } : { opacity: 0, y: 28 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [...ease], delay: 0.08 }}
            className="mx-auto max-w-4xl font-display text-5xl font-bold leading-[1.05] tracking-tight sm:text-7xl"
          >
            Upload raw footage.
            <br />
            Get a <span style={{ background: "var(--brand-gradient)", WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>pro edit</span> back.
          </motion.h1>
          <motion.p
            initial={reduce ? { opacity: 1 } : { opacity: 0, y: 28 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [...ease], delay: 0.16 }}
            className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-[var(--muted-fg)]"
          >
            CutPilot AI transcribes, analyzes and edits your video like a professional human editor —
            smart cuts, kinetic typography, B-roll, karaoke captions, sound design — then hands you a
            full timeline for fine-tuning. One click to 1080p.
          </motion.p>
          <motion.div
            initial={reduce ? { opacity: 1 } : { opacity: 0, y: 28 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [...ease], delay: 0.24 }}
            className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row"
          >
            <Link href={user ? "/dashboard" : "/auth/signup"}>
              <Button size="lg" className="min-w-[200px]">Start editing free</Button>
            </Link>
            <Link href="#pipeline">
              <Button size="lg" variant="outline" className="min-w-[200px]">See how it works</Button>
            </Link>
          </motion.div>

          {/* mock editor window */}
          <motion.div
            initial={reduce ? { opacity: 1 } : { opacity: 0, y: 48, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.7, ease: [...ease], delay: 0.35 }}
            className="mx-auto mt-16 max-w-5xl overflow-hidden rounded-2xl border border-[var(--border-strong)] bg-[var(--card)] text-left shadow-[0_40px_120px_-20px_rgba(225,29,72,0.25)]"
          >
            <div className="flex items-center gap-2 border-b border-[var(--border)] px-4 py-3">
              {["#ef4444", "#f59e0b", "#22c55e"].map((c) => (
                <span key={c} className="h-3 w-3 rounded-full" style={{ background: c }} />
              ))}
              <span className="ml-2 text-xs text-[var(--muted-fg)]">CutPilot AI — timeline.mp4</span>
            </div>
            <div className="grid gap-4 p-5">
              <div className="relative aspect-video overflow-hidden rounded-xl bg-[var(--surface)]">
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="k-scale-pop font-display text-4xl font-bold sm:text-5xl">
                    Every word, <span style={{ color: "var(--accent)" }}>on screen.</span>
                  </span>
                </div>
                <div className="absolute bottom-6 left-0 right-0 flex justify-center">
                  <span className="rounded-lg bg-black/70 px-4 py-2 text-lg font-semibold">
                    <span className="karaoke-word active">Kinetic</span>{" "}
                    <span className="karaoke-word">captions,</span>{" "}
                    <span className="karaoke-word">synced</span>{" "}
                    <span className="karaoke-word">word-by-word</span>
                  </span>
                </div>
                <div className="absolute inset-x-0 top-0 h-1" style={{ background: "var(--brand-gradient)" }} />
              </div>
              <div className="space-y-1.5">
                {[
                  { label: "Video", color: "var(--track-video)", segs: [[0, 32], [38, 70], [76, 100]] },
                  { label: "Text", color: "var(--track-text)", segs: [[8, 22], [44, 58], [80, 92]] },
                  { label: "Captions", color: "var(--track-captions)", segs: [[0, 100]] },
                  { label: "Music", color: "var(--track-music)", segs: [[0, 100]] },
                ].map((t, i) => (
                  <div key={t.label} className="flex items-center gap-2">
                    <span className="w-16 text-[10px] font-semibold uppercase text-[var(--muted-fg)]">{t.label}</span>
                    <div className="relative h-5 flex-1 rounded bg-[var(--muted-bg)]">
                      {t.segs.map(([s, e], j) => (
                        <motion.div
                          key={j}
                          initial={reduce ? {} : { scaleX: 0 }}
                          animate={{ scaleX: 1 }}
                          transition={{ duration: 0.5, delay: 0.5 + i * 0.08 + j * 0.05, ease: [...ease] }}
                          className="absolute top-0 h-full origin-left rounded"
                          style={{ left: `${s}%`, width: `${e - s}%`, background: t.color, opacity: 0.85 }}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* FEATURES */}
      <section className="mx-auto max-w-7xl px-4 py-24 sm:px-6">
        <Stagger className="text-center">
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-[var(--accent)]">The studio</p>
          <h2 className="mt-3 font-display text-4xl font-bold sm:text-5xl">Everything a pro editor does.<br />Automatic.</h2>
        </Stagger>
        <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f, i) => (
            <motion.div
              key={f.title}
              initial={reduce ? { opacity: 1 } : { opacity: 0, scale: 0.92, y: 16 }}
              whileInView={{ opacity: 1, scale: 1, y: 0 }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{ duration: 0.4, ease: "backOut", delay: (i % 3) * 0.06 }}
            >
              <Card className="group h-full p-6 transition-colors duration-150 hover:border-[var(--accent)]">
                <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-[var(--accent-soft)] transition-transform duration-150 group-hover:scale-110">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.8">
                    <path strokeLinecap="round" strokeLinejoin="round" d={f.icon} />
                  </svg>
                </div>
                <h3 className="font-display text-lg font-semibold">{f.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-[var(--muted-fg)]">{f.body}</p>
              </Card>
            </motion.div>
          ))}
        </div>
      </section>

      {/* PIPELINE */}
      <section id="pipeline" className="border-y border-[var(--border)] bg-[var(--card)]">
        <div className="mx-auto max-w-7xl px-4 py-24 sm:px-6">
          <Stagger className="text-center">
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-[var(--accent)]">Pipeline</p>
            <h2 className="mt-3 font-display text-4xl font-bold sm:text-5xl">Raw footage in.<br />Finished video out.</h2>
          </Stagger>
          <div className="mt-14 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {PIPELINE.map((p, i) => (
              <Stagger key={p.stage} delay={(i % 3) * 0.06}>
                <div className="flex h-full gap-4 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface)] p-5">
                  <span className="font-display text-3xl font-bold text-[var(--accent)]">{String(i + 1).padStart(2, "0")}</span>
                  <div>
                    <h3 className="font-display text-base font-semibold">{p.stage}</h3>
                    <p className="mt-1.5 text-sm leading-relaxed text-[var(--muted-fg)]">{p.detail}</p>
                  </div>
                </div>
              </Stagger>
            ))}
          </div>
        </div>
      </section>

      {/* PRICING */}
      <section className="mx-auto max-w-7xl px-4 py-24 sm:px-6">
        <Stagger className="text-center">
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-[var(--accent)]">Pricing</p>
          <h2 className="mt-3 font-display text-4xl font-bold sm:text-5xl">Pay per minute. Nothing else.</h2>
          <p className="mx-auto mt-4 max-w-xl text-[var(--muted-fg)]">1 credit = 1 minute of processed video. No subscription lock-in. Failed jobs never consume credits.</p>
        </Stagger>
        <div className="mt-14 grid gap-5 lg:grid-cols-3">
          {PLANS.map((p, i) => (
            <motion.div
              key={p.name}
              initial={reduce ? { opacity: 1 } : { opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.45, ease: [...ease], delay: i * 0.08 }}
            >
              <Card className={`relative flex h-full flex-col p-7 ${p.popular ? "border-[var(--accent)] shadow-glow" : ""}`}>
                {p.popular && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full px-3 py-1 text-xs font-bold text-white" style={{ background: "var(--brand-gradient)" }}>
                    MOST POPULAR
                  </span>
                )}
                <h3 className="font-display text-xl font-semibold">{p.name}</h3>
                <p className="mt-1 text-sm text-[var(--muted-fg)]">{p.blurb}</p>
                <div className="mt-4 flex items-baseline gap-2">
                  <span className="font-display text-5xl font-bold">{p.price}</span>
                  <span className="text-sm text-[var(--muted-fg)]">/ {p.credits}</span>
                </div>
                <ul className="mt-6 flex-1 space-y-2.5 text-sm text-[var(--muted-fg)]">
                  {p.features.map((f) => (
                    <li key={f} className="flex gap-2.5">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--success)" strokeWidth="2.5" className="mt-0.5 shrink-0">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                      {f}
                    </li>
                  ))}
                </ul>
                <Link href="/auth/signup" className="mt-7">
                  <Button variant={p.popular ? "primary" : "outline"} className="w-full" size="lg">
                    Choose {p.name}
                  </Button>
                </Link>
              </Card>
            </motion.div>
          ))}
        </div>
      </section>

      {/* FAQ */}
      <section className="border-t border-[var(--border)] bg-[var(--card)]">
        <div className="mx-auto max-w-3xl px-4 py-24 sm:px-6">
          <Stagger className="text-center">
            <h2 className="font-display text-4xl font-bold">Questions, answered</h2>
          </Stagger>
          <div className="mt-10">
            {FAQS.map((f) => (
              <FaqItem key={f.q} q={f.q} a={f.a} />
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0" style={{ background: "radial-gradient(ellipse 70% 80% at 50% 100%, rgba(225,29,72,0.25), transparent 65%)" }} />
        <div className="relative mx-auto max-w-4xl px-4 py-28 text-center sm:px-6">
          <Stagger>
            <h2 className="font-display text-4xl font-bold sm:text-6xl">Stop editing.<br />Start publishing.</h2>
            <p className="mx-auto mt-5 max-w-xl text-lg text-[var(--muted-fg)]">
              Your first project is on us. Upload a video and watch CutPilot cut, caption and polish it in minutes.
            </p>
            <Link href={user ? "/dashboard" : "/auth/signup"}>
              <Button size="lg" className="mt-8 min-w-[240px]">Get started free</Button>
            </Link>
          </Stagger>
        </div>
      </section>

      <Footer />
    </div>
  );
}
