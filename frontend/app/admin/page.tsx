"use client";
import { useEffect, useState } from "react";
import { Navbar } from "@/components/Navbar";
import { AuthGuard } from "@/components/chrome";
import { Card, Spinner, EmptyState, Button } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { User } from "@/lib/types";

interface Job {
  id: string;
  type?: string;
  project_id?: string;
  status?: string;
  progress?: number;
  created_at?: string;
}

interface Health {
  status?: string;
  db?: string;
  redis?: string;
  workers?: { name?: string; status?: string; queue?: number }[];
  uptime_seconds?: number;
  [k: string]: unknown;
}

export default function AdminPage() {
  const [users, setUsers] = useState<User[] | null>(null);
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setErr(null);
    try {
      const [u, j, h] = await Promise.all([
        api<User[]>("/api/v1/admin/users"),
        api<Job[]>("/api/v1/admin/jobs"),
        api<Health>("/api/v1/admin/health"),
      ]);
      setUsers(Array.isArray(u) ? u : []);
      setJobs(Array.isArray(j) ? j : []);
      setHealth(h);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not reach the admin API.");
      setUsers(null);
      setJobs(null);
      setHealth(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <AuthGuard adminOnly>
      <div className="min-h-screen bg-black">
        <Navbar />
        <main className="mx-auto max-w-7xl px-4 py-10 sm:px-6">
          <div className="mb-8 flex items-center justify-between">
            <div>
              <h1 className="font-display text-3xl font-bold">Admin</h1>
              <p className="mt-1 text-[var(--muted-fg)]">Users, jobs and system health.</p>
            </div>
            <Button variant="outline" onClick={load}>Refresh</Button>
          </div>

          {loading ? (
            <div className="flex justify-center py-20"><Spinner size={32} /></div>
          ) : err ? (
            <EmptyState title="Admin API unavailable" hint={err} action={<Button onClick={load}>Retry</Button>} />
          ) : (
            <>
              <h2 className="mb-3 font-display text-lg font-semibold">System health</h2>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {[
                  { label: "API", value: health?.status ?? "—", ok: health?.status === "ok" },
                  { label: "Database", value: String(health?.db ?? "—"), ok: String(health?.db).toLowerCase().includes("ok") || String(health?.db).toLowerCase().includes("up") },
                  { label: "Redis", value: String(health?.redis ?? "—"), ok: String(health?.redis).toLowerCase().includes("ok") || String(health?.redis).toLowerCase().includes("up") },
                  { label: "Uptime", value: health?.uptime_seconds != null ? `${Math.floor(Number(health.uptime_seconds) / 3600)}h` : "—", ok: true },
                ].map((c) => (
                  <Card key={c.label} className="p-5">
                    <p className="text-xs uppercase tracking-wider text-[var(--muted-fg)]">{c.label}</p>
                    <p className={`mt-1 font-display text-xl font-bold ${c.ok ? "text-[var(--success)]" : "text-[var(--warning)]"}`}>{c.value}</p>
                  </Card>
                ))}
              </div>

              {health?.workers && health.workers.length > 0 && (
                <>
                  <h2 className="mb-3 mt-8 font-display text-lg font-semibold">Render workers</h2>
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    {health.workers.map((w, i) => (
                      <Card key={i} className="p-5">
                        <p className="font-semibold">{w.name ?? `Worker ${i + 1}`}</p>
                        <p className="mt-1 text-sm text-[var(--muted-fg)]">Status: <span className="text-[var(--success)]">{w.status ?? "—"}</span></p>
                        <p className="text-sm text-[var(--muted-fg)]">Queue depth: {w.queue ?? "—"}</p>
                      </Card>
                    ))}
                  </div>
                </>
              )}

              <h2 className="mb-3 mt-8 font-display text-lg font-semibold">Jobs ({jobs?.length ?? 0})</h2>
              <Card className="divide-y divide-[var(--border)]">
                {!jobs?.length && <p className="p-5 text-sm text-[var(--muted-fg)]">No jobs.</p>}
                {jobs?.slice(0, 20).map((j) => (
                  <div key={j.id} className="flex flex-wrap items-center justify-between gap-2 px-5 py-3 text-sm">
                    <span className="font-mono text-xs text-[var(--muted-fg)]">#{j.id.slice(0, 8)}</span>
                    <span className="font-semibold">{j.type ?? "job"}</span>
                    <span className="text-[var(--muted-fg)]">{j.project_id ? `project ${j.project_id.slice(0, 8)}` : ""}</span>
                    <span className="text-[var(--muted-fg)]">{j.progress != null ? `${Math.round(j.progress)}%` : ""}</span>
                    <span className="rounded-full bg-[var(--muted-bg)] px-2.5 py-0.5 text-xs font-semibold">{j.status ?? "—"}</span>
                  </div>
                ))}
              </Card>

              <h2 className="mb-3 mt-8 font-display text-lg font-semibold">Users ({users?.length ?? 0})</h2>
              <Card className="overflow-x-auto">
                <table className="w-full min-w-[560px] text-left text-sm">
                  <thead>
                    <tr className="border-b border-[var(--border)] text-xs uppercase tracking-wider text-[var(--muted-fg)]">
                      <th className="px-5 py-3">Email</th>
                      <th className="px-5 py-3">Name</th>
                      <th className="px-5 py-3">Role</th>
                      <th className="px-5 py-3">Credits</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border)]">
                    {users?.map((u) => (
                      <tr key={u.id} className="hover:bg-[var(--surface)]">
                        <td className="px-5 py-3 font-medium">{u.email}</td>
                        <td className="px-5 py-3 text-[var(--muted-fg)]">{u.name ?? "—"}</td>
                        <td className="px-5 py-3">
                          <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${u.role === "admin" ? "bg-[var(--accent-soft)] text-[var(--accent)]" : "bg-[var(--muted-bg)] text-[var(--muted-fg)]"}`}>
                            {u.role}
                          </span>
                        </td>
                        <td className="px-5 py-3 font-mono">{u.credits ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            </>
          )}
        </main>
      </div>
    </AuthGuard>
  );
}
