"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { AuthGuard } from "@/components/chrome";
import { Button, Card, ProgressBar, Spinner, EmptyState } from "@/components/ui";
import { api, apiBase, fmtTime, ApiError } from "@/lib/api";
import { useProgress } from "@/hooks/useProgress";
import type { RenderJob, ShortClip, Project } from "@/lib/types";

const PRESETS = [
  { id: "1080p", name: "Full HD 1080p", desc: "1920×1080 · H.264 · default", badge: "DEFAULT" },
  { id: "4k", name: "4K Ultra HD", desc: "3840×2160 · H.264", badge: null },
  { id: "720p", name: "HD 720p draft", desc: "1280×720 · fast draft", badge: null },
  { id: "9:16", name: "Vertical 9:16", desc: "1080×1920 · auto-reframed for Shorts/Reels", badge: "SHORTS" },
  { id: "1:1", name: "Square 1:1", desc: "1080×1080 · feed posts", badge: null },
];

export default function ExportPage() {
  const params = useParams();
  const id = params.id as string;
  const [project, setProject] = useState<Project | null>(null);
  const [renders, setRenders] = useState<RenderJob[]>([]);
  const [shorts, setShorts] = useState<ShortClip[] | null>(null);
  const [thumbs, setThumbs] = useState<{ url: string; label?: string }[] | null>(null);
  const [chapters, setChapters] = useState<{ time: number; title: string }[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const { progress } = useProgress(id, true);

  // Defensive: the API may return {detail} or a wrapped object on some paths —
  // never let a non-array reach .map() in the render below.
  const asArray = <T,>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);

  const load = useCallback(async () => {
    try {
      const [p, rs] = await Promise.all([
        api<Project>(`/api/v1/projects/${id}`).catch(() => null),
        api<RenderJob[]>(`/api/v1/projects/${id}/renders`).catch(() =>
          api<RenderJob[]>(`/api/v1/renders`).catch(() => [])
        ),
      ]);
      setProject(p);
      const list = Array.isArray(rs) ? rs : [];
      setRenders(list.filter((r) => !r.project_id || r.project_id === id).slice(0, 10));
      const sh = await api<unknown>(`/api/v1/projects/${id}/shorts`).catch(() => null);
      setShorts(asArray<ShortClip>(sh));
      const th = await api<unknown>(`/api/v1/projects/${id}/thumbnails`).catch(() => null);
      setThumbs(asArray<{ url: string; label?: string }>(th));
      const ch = await api<unknown>(`/api/v1/projects/${id}/chapters`).catch(() => null);
      setChapters(asArray<{ time: number; title: string }>(ch));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not reach the API.");
    }
  }, [id]);

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  const startRender = async (preset: string) => {
    setBusy(preset);
    setErr(null);
    try {
      await api(`/api/v1/projects/${id}/render`, { method: "POST", body: JSON.stringify({ preset }) });
      load();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Render failed to start.");
    } finally {
      setBusy(null);
    }
  };

  const extractShorts = async () => {
    setBusy("shorts");
    try {
      await api(`/api/v1/projects/${id}/shorts/extract`, { method: "POST" });
      const sh = await api<unknown>(`/api/v1/projects/${id}/shorts`).catch(() => null);
      setShorts(asArray<ShortClip>(sh));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Shorts extraction failed.");
    } finally {
      setBusy(null);
    }
  };

  const copy = (text: string, key: string) => {
    void navigator.clipboard.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(null), 1500);
  };

  const dlUrl = (r: RenderJob) =>
    r.download_url
      ? (r.download_url.startsWith("http") ? r.download_url : `${apiBase}${r.download_url}`)
      : `${apiBase}/api/v1/renders/${r.id}/download`;

  return (
    <AuthGuard>
      <div className="min-h-screen bg-black">
        <header className="border-b border-[var(--border)]">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
            <Link href={`/project/${id}/edit`} className="cursor-pointer text-sm text-[var(--muted-fg)] hover:text-white">← Back to editor</Link>
            <span className="font-display font-semibold">{project?.name ?? "Export"}</span>
            <span className="w-24" />
          </div>
        </header>

        <main className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
          <h1 className="font-display text-3xl font-bold">Render & export</h1>
          <p className="mt-1 text-[var(--muted-fg)]">Pick a preset. Rendering starts only when you click — never automatically.</p>
          {err && <p className="mt-4 text-sm text-[var(--destructive)]">{err}</p>}

          {/* presets */}
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {PRESETS.map((p) => (
              <Card key={p.id} className="relative flex flex-col p-5">
                {p.badge && (
                  <span className="absolute right-3 top-3 rounded-full px-2 py-0.5 text-[10px] font-bold text-white" style={{ background: "var(--brand-gradient)" }}>
                    {p.badge}
                  </span>
                )}
                <h3 className="font-display font-semibold">{p.name}</h3>
                <p className="mt-1 flex-1 text-xs text-[var(--muted-fg)]">{p.desc}</p>
                <Button size="sm" className="mt-4 w-full" onClick={() => startRender(p.id)} disabled={busy === p.id}>
                  {busy === p.id ? "Starting…" : "Render"}
                </Button>
              </Card>
            ))}
          </div>

          {/* queue */}
          <h2 className="mt-12 font-display text-xl font-bold">Render queue</h2>
          {progress && (progress.stage.toLowerCase().includes("render") || progress.pct > 0) && (
            <Card className="mt-4 p-5">
              <div className="mb-2 flex items-center justify-between text-sm">
                <span className="font-semibold capitalize">{progress.stage.replace(/_/g, " ")}</span>
                <span className="text-[var(--muted-fg)]">{Math.round(progress.pct)}%</span>
              </div>
              <ProgressBar pct={progress.pct} />
              {progress.message && <p className="mt-2 text-xs text-[var(--muted-fg)]">{progress.message}</p>}
            </Card>
          )}
          <div className="mt-4 space-y-3">
            {renders.length === 0 && (
              <Card className="p-5 text-sm text-[var(--muted-fg)]">No renders yet. Start one above.</Card>
            )}
            {renders.map((r) => (
              <Card key={r.id} className="flex flex-wrap items-center gap-4 p-5">
                <div className="min-w-0 flex-1">
                  <p className="font-semibold">{r.preset ?? "Render"} <span className="font-mono text-xs text-[var(--muted-fg)]">#{r.id.slice(0, 8)}</span></p>
                  {(r.status === "rendering" || r.status === "queued") && (
                    <div className="mt-2 flex items-center gap-3">
                      <ProgressBar pct={r.progress ?? 0} className="max-w-xs" />
                      <span className="text-xs text-[var(--muted-fg)]">
                        {Math.round(r.progress ?? 0)}%
                        {r.eta_seconds != null ? ` · ETA ${fmtTime(r.eta_seconds)}` : ""}
                      </span>
                    </div>
                  )}
                </div>
                <span className={`rounded-full px-3 py-1 text-xs font-semibold ${
                  r.status === "done" ? "bg-[rgba(34,197,94,0.15)] text-[var(--success)]" :
                  r.status === "failed" ? "bg-[rgba(239,68,68,0.15)] text-[var(--destructive)]" :
                  "bg-[rgba(99,102,241,0.18)] text-[#a5b4fc]"
                }`}>{r.status}</span>
                {r.status === "done" && (
                  <>
                    <a href={dlUrl(r)} download>
                      <Button size="sm">Download MP4</Button>
                    </a>
                    <Button size="sm" variant="outline" onClick={() => copy(dlUrl(r), r.id)}>
                      {copied === r.id ? "Copied!" : "Copy share link"}
                    </Button>
                  </>
                )}
              </Card>
            ))}
          </div>

          {/* YouTube stub */}
          <Card className="mt-8 flex flex-wrap items-center justify-between gap-4 p-5">
            <div>
              <h3 className="font-display font-semibold">Publish to YouTube</h3>
              <p className="text-sm text-[var(--muted-fg)]">Direct upload via the YouTube API — connect your channel to enable.</p>
            </div>
            <Button variant="outline" disabled title="YouTube API connection required (Worker A/B)">
              Connect channel
            </Button>
          </Card>

          {/* shorts */}
          <div className="mt-12 flex items-center justify-between">
            <h2 className="font-display text-xl font-bold">Shorts extractor</h2>
            <Button variant="soft" onClick={extractShorts} disabled={busy === "shorts"}>
              {busy === "shorts" ? "Extracting…" : shorts?.length ? "Re-extract" : "Extract 3 best clips"}
            </Button>
          </div>
          {shorts === null ? (
            <p className="mt-3 text-sm text-[var(--muted-fg)]">Shorts aren't available on this server yet.</p>
          ) : shorts.length === 0 ? (
            <Card className="mt-3 p-5 text-sm text-[var(--muted-fg)]">No shorts yet — the AI will pick the 3 best 30–60s vertical moments.</Card>
          ) : (
            <div className="mt-4 grid gap-4 sm:grid-cols-3">
              {shorts.map((s) => (
                <Card key={s.id} className="overflow-hidden">
                  <div className="flex aspect-[9/16] max-h-64 items-center justify-center bg-[var(--surface)]">
                    {s.thumbnail_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={s.thumbnail_url.startsWith("http") ? s.thumbnail_url : `${apiBase}${s.thumbnail_url}`} alt={s.title ?? "short"} className="h-full w-full object-cover" />
                    ) : (
                      <span className="text-4xl font-bold text-[var(--border-strong)]">9:16</span>
                    )}
                  </div>
                  <div className="p-4">
                    <p className="truncate font-semibold">{s.title ?? `Clip ${fmtTime(s.start)}`}</p>
                    <p className="text-xs text-[var(--muted-fg)]">{fmtTime(s.start)} → {fmtTime(s.end)}{s.score != null ? ` · score ${Math.round(s.score)}` : ""}</p>
                    {s.download_url && (
                      <a href={s.download_url.startsWith("http") ? s.download_url : `${apiBase}${s.download_url}`} download>
                        <Button size="sm" variant="outline" className="mt-3 w-full">Download</Button>
                      </a>
                    )}
                  </div>
                </Card>
              ))}
            </div>
          )}

          {/* thumbnails + chapters */}
          <div className="mt-12 grid gap-8 lg:grid-cols-2">
            <div>
              <h2 className="font-display text-xl font-bold">AI thumbnails</h2>
              {thumbs === null ? (
                <p className="mt-3 text-sm text-[var(--muted-fg)]">Thumbnails aren't available on this server yet.</p>
              ) : thumbs.length === 0 ? (
                <Card className="mt-3 p-5 text-sm text-[var(--muted-fg)]">No thumbnails generated yet.</Card>
              ) : (
                <div className="mt-4 grid gap-3 sm:grid-cols-3">
                  {thumbs.map((t, i) => (
                    <a key={i} href={t.url.startsWith("http") ? t.url : `${apiBase}${t.url}`} download className="cursor-pointer">
                      <Card className="overflow-hidden transition-colors hover:border-[var(--accent)]">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={t.url.startsWith("http") ? t.url : `${apiBase}${t.url}`} alt={t.label ?? `Thumbnail ${i + 1}`} className="aspect-video w-full object-cover" />
                        <p className="p-2 text-center text-xs text-[var(--muted-fg)]">{t.label ?? `Option ${i + 1}`}</p>
                      </Card>
                    </a>
                  ))}
                </div>
              )}
            </div>
            <div>
              <div className="flex items-center justify-between">
                <h2 className="font-display text-xl font-bold">Auto chapters</h2>
                {chapters && chapters.length > 0 && (
                  <Button size="sm" variant="outline" onClick={() => copy(chapters.map((c) => `${fmtTime(c.time)} ${c.title}`).join("\n"), "chapters")}>
                    {copied === "chapters" ? "Copied!" : "Copy all"}
                  </Button>
                )}
              </div>
              {chapters === null ? (
                <p className="mt-3 text-sm text-[var(--muted-fg)]">Chapters aren't available on this server yet.</p>
              ) : chapters.length === 0 ? (
                <Card className="mt-3 p-5 text-sm text-[var(--muted-fg)]">No chapters generated yet.</Card>
              ) : (
                <Card className="mt-4 divide-y divide-[var(--border)]">
                  {chapters.map((c, i) => (
                    <div key={i} className="flex items-center justify-between px-4 py-2.5 text-sm">
                      <span className="font-mono text-[var(--accent)]">{fmtTime(c.time)}</span>
                      <span className="flex-1 px-3">{c.title}</span>
                      <button onClick={() => copy(`${fmtTime(c.time)} ${c.title}`, `ch${i}`)} className="cursor-pointer text-xs text-[var(--muted-fg)] hover:text-white">
                        {copied === `ch${i}` ? "Copied" : "Copy"}
                      </button>
                    </div>
                  ))}
                </Card>
              )}
            </div>
          </div>
        </main>
      </div>
    </AuthGuard>
  );
}
