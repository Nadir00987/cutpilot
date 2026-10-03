"use client";
import { useEffect, useRef, useState } from "react";
import { Navbar } from "@/components/Navbar";
import { AuthGuard } from "@/components/chrome";
import { Button, Card, Select, Label, Spinner, ProgressBar } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { Project } from "@/lib/types";

interface BatchJob {
  id: string;
  filename?: string;
  project_id?: string;
  status?: string;
  progress?: number;
}

export default function BatchPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [preset, setPreset] = useState("balanced");
  const [jobs, setJobs] = useState<BatchJob[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [supported, setSupported] = useState(true);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api<BatchJob[]>("/api/v1/batch/jobs")
      .then((j) => setJobs(Array.isArray(j) ? j : []))
      .catch(() => {
        setJobs(null);
        setSupported(false);
      });
  }, []);

  const start = async () => {
    if (!files.length) return;
    setBusy(true);
    setMsg(null);
    try {
      const started: BatchJob[] = [];
      for (const f of files) {
        const p = await api<Project>("/api/v1/projects", {
          method: "POST",
          body: JSON.stringify({ name: f.name.replace(/\.[^.]+$/, "") }),
        });
        const fd = new FormData();
        fd.append("file", f);
        await api(`/api/v1/projects/${p.id}/upload`, { method: "POST", body: fd });
        await api(`/api/v1/projects/${p.id}/analyze`, { method: "POST", body: JSON.stringify({ preset }) }).catch(() => null);
        started.push({ id: p.id, filename: f.name, project_id: p.id, status: "analyzing", progress: 0 });
      }
      setJobs((j) => [...(j ?? []), ...started]);
      setFiles([]);
      setMsg(`${started.length} videos queued — same "${preset}" style applied to all. They'll process overnight in order.`);
    } catch (e) {
      setMsg(e instanceof ApiError ? `Batch failed: ${e.message}` : "Batch failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthGuard>
      <div className="min-h-screen bg-black">
        <Navbar />
        <main className="mx-auto max-w-4xl px-4 py-10 sm:px-6">
          <h1 className="font-display text-3xl font-bold">Batch processing</h1>
          <p className="mt-1 text-[var(--muted-fg)]">Upload up to 10 videos — one style preset applied to all, processed in an overnight queue.</p>

          <Card className="mt-8 p-6">
            <div className="flex flex-wrap gap-4">
              <div className="min-w-[200px] flex-1">
                <Label>Style preset</Label>
                <Select value={preset} onChange={(e) => setPreset(e.target.value)} className="w-full">
                  <option value="fast">Fast — punchy</option>
                  <option value="balanced">Balanced</option>
                  <option value="calm">Calm — educational</option>
                </Select>
              </div>
              <div className="flex items-end">
                <input ref={fileRef} type="file" accept="video/*" multiple className="hidden" onChange={(e) => setFiles(Array.from(e.target.files ?? []).slice(0, 10))} />
                <Button variant="outline" onClick={() => fileRef.current?.click()}>Choose files (max 10)</Button>
              </div>
            </div>
            {files.length > 0 && (
              <ul className="mt-4 space-y-1 text-sm text-[var(--muted-fg)]">
                {files.map((f) => <li key={f.name}>• {f.name} <span className="text-xs">({(f.size / 1e6).toFixed(1)} MB)</span></li>)}
              </ul>
            )}
            <div className="mt-5">
              <Button onClick={start} disabled={busy || files.length === 0}>
                {busy ? "Uploading…" : `Queue ${files.length} video${files.length === 1 ? "" : "s"}`}
              </Button>
            </div>
            {msg && <p className="mt-3 text-sm text-[var(--accent)]">{msg}</p>}
          </Card>

          <h2 className="mb-3 mt-8 font-display text-lg font-semibold">Queue</h2>
          {jobs === null && !supported ? (
            <Card className="p-5 text-sm text-[var(--muted-fg)]">
              The dedicated batch endpoint isn't on this server yet — uploads above still create individual projects with the same preset.
            </Card>
          ) : jobs === null ? (
            <div className="flex justify-center py-10"><Spinner /></div>
          ) : jobs.length === 0 ? (
            <Card className="p-5 text-sm text-[var(--muted-fg)]">Queue is empty.</Card>
          ) : (
            <div className="space-y-3">
              {jobs.map((j) => (
                <Card key={j.id} className="p-4">
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-semibold">{j.filename ?? j.id.slice(0, 8)}</span>
                    <span className="text-[var(--muted-fg)]">{j.status ?? "queued"}</span>
                  </div>
                  <ProgressBar pct={j.progress ?? 0} className="mt-2" />
                </Card>
              ))}
            </div>
          )}
        </main>
      </div>
    </AuthGuard>
  );
}
