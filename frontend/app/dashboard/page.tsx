"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import { Navbar } from "@/components/Navbar";
import { AuthGuard, StatusBadge } from "@/components/chrome";
import { Button, Card, Input, Select, EmptyState, Spinner } from "@/components/ui";
import { api, apiBase, fmtTime, fmtCredits, ApiError } from "@/lib/api";
import type { Project, RenderJob } from "@/lib/types";

function UploadZone({ onDone }: { onDone: (p: Project) => void }) {
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [urlMode, setUrlMode] = useState(false);
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const uploadFile = useCallback(
    async (file: File) => {
      setBusy(true);
      setErr(null);
      try {
        // 1. create project
        const project = await api<Project>("/api/v1/projects", {
          method: "POST",
          body: JSON.stringify({ name: name || file.name.replace(/\.[^.]+$/, "") }),
        });
        // 2. upload file
        const fd = new FormData();
        fd.append("file", file);
        await api(`/api/v1/projects/${project.id}/upload`, { method: "POST", body: fd });
        // 3. kick off analysis
        try {
          await api(`/api/v1/projects/${project.id}/analyze`, { method: "POST" });
        } catch {
          /* analysis endpoint may differ; analyze page can trigger */
        }
        onDone(project);
      } catch (e) {
        setErr(e instanceof ApiError ? e.message : "Upload failed. Is the API running at " + apiBase + "?");
      } finally {
        setBusy(false);
      }
    },
    [name, onDone]
  );

  const importUrl = async () => {
    if (!url.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      const project = await api<Project>("/api/v1/projects", {
        method: "POST",
        body: JSON.stringify({ name: name || "Imported video" }),
      });
      await api(`/api/v1/projects/${project.id}/import-url`, {
        method: "POST",
        body: JSON.stringify({ url }),
      });
      onDone(project);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Import failed. Is the API running?");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="p-6">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-display text-lg font-semibold">New project</h2>
        <button
          onClick={() => setUrlMode(!urlMode)}
          className="cursor-pointer text-sm font-semibold text-[var(--accent)] hover:brightness-125"
        >
          {urlMode ? "Upload a file instead" : "Import from URL"}
        </button>
      </div>
      <Input
        placeholder="Project name (optional)"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="mb-4"
      />
      {urlMode ? (
        <div className="flex gap-2">
          <Input placeholder="YouTube / Drive / direct link…" value={url} onChange={(e) => setUrl(e.target.value)} />
          <Button onClick={importUrl} disabled={busy || !url.trim()}>Import</Button>
        </div>
      ) : (
        <div
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            const f = e.dataTransfer.files?.[0];
            if (f) uploadFile(f);
          }}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-[var(--radius-sm)] border-2 border-dashed px-6 py-10 text-center transition-colors duration-150 ${
            drag ? "border-[var(--accent)] bg-[var(--accent-soft)]" : "border-[var(--border-strong)] hover:border-[var(--accent)]"
          }`}
        >
          <input
            ref={fileRef}
            type="file"
            accept="video/*,audio/*,.mkv"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) uploadFile(f);
              e.target.value = "";
            }}
          />
          {busy ? (
            <div className="flex items-center gap-3 text-[var(--muted-fg)]"><Spinner /> Uploading…</div>
          ) : (
            <>
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.6" className="mb-3">
                <path strokeLinecap="round" strokeLinejoin="round" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
              <p className="font-semibold">Drop your footage here, or click to browse</p>
              <p className="mt-1 text-sm text-[var(--muted-fg)]">MP4 · MOV · WebM · MKV · MP3/WAV — up to 4 GB</p>
            </>
          )}
        </div>
      )}
      {err && <p className="mt-3 text-sm text-[var(--destructive)]">{err}</p>}
    </Card>
  );
}

function ProjectCard({ p, index, reduce }: { p: Project; index: number; reduce: boolean }) {
  const thumb = p.thumbnail_url
    ? (p.thumbnail_url.startsWith("http") ? p.thumbnail_url : `${apiBase}${p.thumbnail_url}`)
    : null;
  return (
    <motion.div
      initial={reduce ? { opacity: 1 } : { opacity: 0, scale: 0.94, y: 14 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{ duration: 0.35, delay: Math.min(index, 8) * 0.05, ease: "easeOut" }}
    >
      <Link href={`/project/${p.id}/${p.status === "analyzing" || p.status === "uploading" ? "analyze" : "edit"}`}>
        <Card className="group h-full cursor-pointer overflow-hidden transition-colors duration-150 hover:border-[var(--accent)]">
          <div className="relative aspect-video bg-[var(--surface)]">
            {thumb ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={thumb} alt={p.name} className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full w-full items-center justify-center">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--border-strong)" strokeWidth="1.5">
                  <path d="M23 7l-7 5 7 5V7z" /><rect x="1" y="5" width="15" height="14" rx="2" />
                </svg>
              </div>
            )}
            <div className="absolute left-2 top-2"><StatusBadge status={p.status} /></div>
            {p.duration != null && (
              <span className="absolute bottom-2 right-2 rounded bg-black/70 px-1.5 py-0.5 text-xs font-semibold">{fmtTime(p.duration)}</span>
            )}
          </div>
          <div className="p-4">
            <h3 className="truncate font-display font-semibold group-hover:text-white">{p.name}</h3>
            <p className="mt-1 text-xs text-[var(--muted-fg)]">
              {p.created_at ? new Date(p.created_at).toLocaleDateString() : ""}
              {p.width && p.height ? ` · ${p.width}×${p.height}` : ""}
            </p>
          </div>
        </Card>
      </Link>
    </motion.div>
  );
}

export default function DashboardPage() {
  const reduce = useReducedMotion() ?? false;
  const [projects, setProjects] = useState<Project[]>([]);
  const [renders, setRenders] = useState<RenderJob[]>([]);
  const [credits, setCredits] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [ps, rs, bal] = await Promise.all([
        api<Project[]>("/api/v1/projects").catch(() => []),
        api<RenderJob[]>("/api/v1/renders").catch(() => []),
        api<{ credits: number }>("/api/v1/billing/credits").catch(() => null),
      ]);
      setProjects(Array.isArray(ps) ? ps : (ps as { items?: Project[] })?.items ?? []);
      setRenders(Array.isArray(rs) ? rs.slice(0, 5) : []);
      setCredits(bal?.credits ?? null);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not reach the API.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = projects.filter((p) => {
    const q = query.toLowerCase();
    const okQ = !q || p.name.toLowerCase().includes(q);
    const okF = filter === "all" || p.status === filter;
    return okQ && okF;
  });

  return (
    <AuthGuard>
      <div className="min-h-screen bg-black">
        <Navbar />
        <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
          <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
            <div>
              <h1 className="font-display text-3xl font-bold">Studio dashboard</h1>
              <p className="mt-1 text-[var(--muted-fg)]">Your projects, renders and credits in one place.</p>
            </div>
            <Card className="flex items-center gap-3 px-5 py-3">
              <div>
                <p className="text-xs uppercase tracking-wider text-[var(--muted-fg)]">Credits</p>
                <p className="font-display text-2xl font-bold text-[var(--accent)]">{fmtCredits(credits)}</p>
              </div>
              <Link href="/billing"><Button size="sm" variant="soft">Top up</Button></Link>
            </Card>
          </div>

          <div className="grid gap-8 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <UploadZone onDone={() => load()} />
              <div className="mt-8 mb-4 flex flex-wrap items-center justify-between gap-3">
                <h2 className="font-display text-lg font-semibold">Projects ({filtered.length})</h2>
                <div className="flex gap-2">
                  <Input placeholder="Search projects…" value={query} onChange={(e) => setQuery(e.target.value)} className="!w-48" />
                  <Select value={filter} onChange={(e) => setFilter(e.target.value)}>
                    <option value="all">All statuses</option>
                    <option value="uploading">Uploading</option>
                    <option value="analyzing">Analyzing</option>
                    <option value="ready">Ready</option>
                    <option value="rendering">Rendering</option>
                    <option value="done">Done</option>
                    <option value="error">Error</option>
                  </Select>
                </div>
              </div>
              {loading ? (
                <div className="flex justify-center py-16"><Spinner size={32} /></div>
              ) : err ? (
                <EmptyState title="Couldn't reach the API" hint={err + " Start the backend (Worker A) and reload."} action={<Button onClick={load}>Retry</Button>} />
              ) : filtered.length === 0 ? (
                <EmptyState title="No projects yet" hint="Upload your first video above and CutPilot will transcribe, analyze and edit it automatically." />
              ) : (
                <div className="grid gap-5 sm:grid-cols-2">
                  {filtered.map((p, i) => (
                    <ProjectCard key={p.id} p={p} index={i} reduce={reduce} />
                  ))}
                </div>
              )}
            </div>
            <div>
              <h2 className="mb-4 font-display text-lg font-semibold">Recent renders</h2>
              {renders.length === 0 ? (
                <Card className="p-5 text-sm text-[var(--muted-fg)]">No renders yet. Export a project to see it here.</Card>
              ) : (
                <div className="space-y-3">
                  {renders.map((r) => (
                    <Card key={r.id} className="flex items-center justify-between gap-3 p-4">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold">{r.preset ?? "Render"}</p>
                        <p className="text-xs text-[var(--muted-fg)]">{r.created_at ? new Date(r.created_at).toLocaleString() : ""}</p>
                      </div>
                      <StatusBadge status={r.status} />
                    </Card>
                  ))}
                </div>
              )}
              <div className="mt-6 space-y-2">
                <Link href="/batch"><Button variant="outline" className="w-full">Batch processing</Button></Link>
                <Link href="/teams"><Button variant="outline" className="w-full">Team workspaces</Button></Link>
                <Link href="/voiceover"><Button variant="outline" className="w-full">Voiceover studio</Button></Link>
              </div>
            </div>
          </div>
        </main>
      </div>
    </AuthGuard>
  );
}
