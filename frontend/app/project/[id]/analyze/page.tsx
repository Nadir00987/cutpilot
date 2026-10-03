"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import { AuthGuard } from "@/components/chrome";
import { Button, Card, ProgressBar, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useProgress } from "@/hooks/useProgress";
import type { Analysis, Project } from "@/lib/types";

const STAGES = [
  { key: "transcription", label: "Transcription", desc: "Word-level speech-to-text, language auto-detect" },
  { key: "filler", label: "Filler detection", desc: "umms, repeats, false starts → tagged, not deleted" },
  { key: "silence", label: "Silence detection", desc: "Dead air > 0.8s flagged for removal" },
  { key: "scenes", label: "Scene analysis", desc: "Shot detection + vision description per scene" },
  { key: "diarization", label: "Speaker diarization", desc: "Speaker turns labeled for interviews/podcasts" },
  { key: "energy", label: "Energy scoring", desc: "Loudness + speech rate → highlight candidates" },
  { key: "hook", label: "Hook detection", desc: "Strongest 3–5s opening candidate" },
  { key: "keywords", label: "Keyword extraction", desc: "Drives kinetic text + B-roll matching" },
  { key: "audio", label: "Audio QC", desc: "Noise, clipping, volume consistency" },
  { key: "summary", label: "Summary", desc: "Summary, suggested title, thumbnail text" },
  { key: "planning", label: "Edit planning", desc: "Smart cuts, graphics, captions — the AI edit plan" },
];

function stageState(stageKey: string, current: string | null): "done" | "active" | "todo" {
  if (!current) return "todo";
  const order = STAGES.map((s) => s.key);
  const curIdx = order.findIndex((k) => current.toLowerCase().includes(k));
  const myIdx = order.indexOf(stageKey);
  if (curIdx === -1) return "todo";
  if (myIdx < curIdx) return "done";
  if (myIdx === curIdx) return "active";
  return "todo";
}

export default function AnalyzePage() {
  const params = useParams();
  const id = params.id as string;
  const router = useRouter();
  const [project, setProject] = useState<Project | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const { progress, connected } = useProgress(id, true);

  const done = project?.status === "ready" || project?.status === "done" || !!analysis?.transcript;

  const refresh = useCallback(async () => {
    try {
      const [p, a] = await Promise.all([
        api<Project>(`/api/v1/projects/${id}`),
        api<Analysis>(`/api/v1/projects/${id}/analysis`).catch(() => null),
      ]);
      setProject(p);
      setAnalysis(a);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not reach the API.");
    }
  }, [id]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 8000);
    return () => clearInterval(t);
  }, [refresh]);

  const start = async () => {
    setStarting(true);
    setErr(null);
    try {
      await api(`/api/v1/projects/${id}/analyze`, { method: "POST" });
      refresh();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Failed to start analysis.");
    } finally {
      setStarting(false);
    }
  };

  const currentStage = progress?.stage ?? null;

  return (
    <AuthGuard>
      <div className="min-h-screen bg-black">
        <header className="border-b border-[var(--border)]">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4 sm:px-6">
            <Link href="/dashboard" className="cursor-pointer text-sm text-[var(--muted-fg)] hover:text-white">← Dashboard</Link>
            <span className="font-display font-semibold">{project?.name ?? "Project"}</span>
            <span className={`text-xs font-semibold ${connected ? "text-[var(--success)]" : "text-[var(--muted-fg)]"}`}>
              {connected ? "● live" : "○ connecting"}
            </span>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
          <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
            <div>
              <h1 className="font-display text-3xl font-bold">Deep analysis</h1>
              <p className="mt-1 text-[var(--muted-fg)]">
                {progress?.message ?? "Eleven AI stages run before a single cut is made."}
              </p>
            </div>
            {!done && (
              <Button onClick={start} disabled={starting}>
                {starting ? "Starting…" : project?.status === "analyzing" ? "Analysis running…" : "Run analysis"}
              </Button>
            )}
            {done && (
              <Link href={`/project/${id}/edit`}>
                <Button size="lg">Open timeline editor →</Button>
              </Link>
            )}
          </div>

          {err && <p className="mb-4 text-sm text-[var(--destructive)]">{err}</p>}

          {progress && (
            <Card className="mb-8 p-5">
              <div className="mb-2 flex items-center justify-between text-sm">
                <span className="font-semibold capitalize">{currentStage?.replace(/_/g, " ")}</span>
                <span className="text-[var(--muted-fg)]">{Math.round(progress.pct)}%</span>
              </div>
              <ProgressBar pct={progress.pct} />
            </Card>
          )}

          <div className="space-y-3">
            {STAGES.map((s, i) => {
              const st = done ? "done" : stageState(s.key, currentStage);
              return (
                <motion.div
                  key={s.key}
                  initial={{ opacity: 0, x: -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.04, duration: 0.3 }}
                >
                  <Card className={`flex items-center gap-4 p-4 ${st === "active" ? "border-[var(--accent)]" : ""}`}>
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-bold"
                      style={
                        st === "done"
                          ? { background: "rgba(34,197,94,0.15)", color: "var(--success)" }
                          : st === "active"
                            ? { background: "var(--accent-soft)", color: "var(--accent)" }
                            : { background: "var(--muted-bg)", color: "var(--muted-fg)" }
                      }>
                      {st === "done" ? "✓" : st === "active" ? <Spinner size={16} /> : i + 1}
                    </span>
                    <div>
                      <p className="font-semibold">{s.label}</p>
                      <p className="text-sm text-[var(--muted-fg)]">{s.desc}</p>
                    </div>
                  </Card>
                </motion.div>
              );
            })}
          </div>

          {analysis?.summary && (
            <Card className="mt-8 p-6">
              <h2 className="font-display text-lg font-semibold">Content summary</h2>
              <p className="mt-2 text-sm leading-relaxed text-[var(--muted-fg)]">{analysis.summary}</p>
              {analysis.suggested_title && (
                <p className="mt-3 text-sm"><span className="font-semibold">Suggested title:</span> {analysis.suggested_title}</p>
              )}
              {analysis.keywords && analysis.keywords.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {analysis.keywords.slice(0, 12).map((k, i) => {
                    const label = typeof k === "string" ? k : k?.phrase ?? "";
                    return (
                      <span key={`${label}-${i}`} className="rounded-full bg-[var(--muted-bg)] px-3 py-1 text-xs">{label}</span>
                    );
                  })}
                </div>
              )}
            </Card>
          )}
        </main>
      </div>
    </AuthGuard>
  );
}
