"use client";
import { useEffect, useState } from "react";
import { Navbar } from "@/components/Navbar";
import { AuthGuard } from "@/components/chrome";
import { Button, Card, Input, Label, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

interface Member {
  id: string;
  email: string;
  role?: string;
  name?: string;
}

export default function TeamsPage() {
  const [members, setMembers] = useState<Member[] | null>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("editor");
  const [msg, setMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<Member[]>("/api/v1/teams/members")
      .then((m) => setMembers(Array.isArray(m) ? m : []))
      .catch(() => setMembers(null))
      .finally(() => setLoading(false));
  }, []);

  const invite = async () => {
    if (!email.trim()) return;
    setMsg(null);
    try {
      const m = await api<Member>("/api/v1/teams/invite", {
        method: "POST",
        body: JSON.stringify({ email, role }),
      });
      setMembers((ms) => (ms ? [...ms, m] : [m]));
      setEmail("");
      setMsg(`Invite sent to ${email}.`);
    } catch (e) {
      setMsg(e instanceof ApiError ? `Invite failed: ${e.message}` : "Invite failed.");
    }
  };

  return (
    <AuthGuard>
      <div className="min-h-screen bg-black">
        <Navbar />
        <main className="mx-auto max-w-4xl px-4 py-10 sm:px-6">
          <h1 className="font-display text-3xl font-bold">Team workspace</h1>
          <p className="mt-1 text-[var(--muted-fg)]">Invite editors and viewers. Teammates can leave timestamped comments on any project.</p>

          {loading ? (
            <div className="flex justify-center py-20"><Spinner size={32} /></div>
          ) : members === null ? (
            <Card className="mt-8 p-8 text-center">
              <p className="font-display text-lg font-semibold">Team features aren't enabled on this server yet</p>
              <p className="mx-auto mt-2 max-w-md text-sm text-[var(--muted-fg)]">
                Invites, roles and shared workspaces are built by Worker E. The timeline editor already includes a
                timestamped comments panel per project for when the API lands.
              </p>
            </Card>
          ) : (
            <>
              <Card className="mt-8 p-6">
                <h2 className="font-display text-lg font-semibold">Invite a teammate</h2>
                <div className="mt-4 flex flex-wrap gap-3">
                  <div className="min-w-[220px] flex-1">
                    <Label>Email</Label>
                    <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="teammate@studio.com" />
                  </div>
                  <div>
                    <Label>Role</Label>
                    <select value={role} onChange={(e) => setRole(e.target.value)} className="rounded-[10px] border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5 text-sm">
                      <option value="editor">Editor</option>
                      <option value="viewer">Viewer</option>
                    </select>
                  </div>
                  <div className="flex items-end">
                    <Button onClick={invite}>Send invite</Button>
                  </div>
                </div>
                {msg && <p className="mt-3 text-sm text-[var(--accent)]">{msg}</p>}
              </Card>

              <h2 className="mb-3 mt-8 font-display text-lg font-semibold">Members ({members.length})</h2>
              <Card className="divide-y divide-[var(--border)]">
                {members.length === 0 && <p className="p-5 text-sm text-[var(--muted-fg)]">No members yet — you're the first.</p>}
                {members.map((m) => (
                  <div key={m.id} className="flex items-center justify-between px-5 py-3 text-sm">
                    <div>
                      <p className="font-semibold">{m.name ?? m.email}</p>
                      {m.name && <p className="text-xs text-[var(--muted-fg)]">{m.email}</p>}
                    </div>
                    <span className="rounded-full bg-[var(--muted-bg)] px-3 py-1 text-xs font-semibold capitalize">{m.role ?? "editor"}</span>
                  </div>
                ))}
              </Card>
            </>
          )}
        </main>
      </div>
    </AuthGuard>
  );
}
