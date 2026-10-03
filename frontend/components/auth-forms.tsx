"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import { Logo } from "@/components/Navbar";
import { Button, Input, Label, Card } from "@/components/ui";

function Shell({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-black px-4 py-12">
      <div className="pointer-events-none fixed inset-0" style={{ background: "radial-gradient(ellipse 60% 50% at 50% 0%, rgba(225,29,72,0.15), transparent 60%)" }} />
      <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45 }} className="relative w-full max-w-md">
        <div className="mb-8 flex justify-center"><Logo /></div>
        <Card className="p-8">
          <h1 className="font-display text-2xl font-bold">{title}</h1>
          <p className="mt-1.5 text-sm text-[var(--muted-fg)]">{subtitle}</p>
          <div className="mt-6">{children}</div>
        </Card>
      </motion.div>
    </div>
  );
}

export function ErrorNote({ err }: { err: string | null }) {
  if (!err) return null;
  return (
    <div className="mb-4 rounded-[10px] border border-[rgba(239,68,68,0.4)] bg-[rgba(239,68,68,0.1)] px-4 py-3 text-sm text-[var(--destructive)]">
      {err}
    </div>
  );
}

export function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await login(email, password);
      router.push("/dashboard");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Login failed. Is the API running?");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell title="Welcome back" subtitle="Log in to your CutPilot studio.">
      <form onSubmit={submit} className="space-y-4">
        <ErrorNote err={err} />
        <div>
          <Label>Email</Label>
          <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@studio.com" autoComplete="email" />
        </div>
        <div>
          <Label>Password</Label>
          <Input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" autoComplete="current-password" />
        </div>
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? "Logging in…" : "Log in"}
        </Button>
        <div className="flex items-center justify-between text-sm">
          <Link href="/auth/forgot-password" className="cursor-pointer text-[var(--muted-fg)] hover:text-white">Forgot password?</Link>
          <Link href="/auth/signup" className="cursor-pointer font-semibold text-[var(--accent)] hover:brightness-125">Create account</Link>
        </div>
      </form>
    </Shell>
  );
}

export function SignupForm() {
  const { signup } = useAuth();
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await signup(name, email, password);
      router.push("/dashboard");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Signup failed. Is the API running?");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell title="Create your studio" subtitle="Free to start. No card required.">
      <form onSubmit={submit} className="space-y-4">
        <ErrorNote err={err} />
        <div>
          <Label>Name</Label>
          <Input required value={name} onChange={(e) => setName(e.target.value)} placeholder="Alex Creator" autoComplete="name" />
        </div>
        <div>
          <Label>Email</Label>
          <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@studio.com" autoComplete="email" />
        </div>
        <div>
          <Label>Password</Label>
          <Input type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Min. 8 characters" autoComplete="new-password" />
        </div>
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? "Creating…" : "Create account"}
        </Button>
        <p className="text-center text-sm text-[var(--muted-fg)]">
          Already have an account?{" "}
          <Link href="/auth/login" className="cursor-pointer font-semibold text-[var(--accent)] hover:brightness-125">Log in</Link>
        </p>
      </form>
    </Shell>
  );
}

export function ForgotForm() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const { api } = await import("@/lib/api");
      await api("/api/v1/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }), auth: false });
      setSent(true);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Request failed. Is the API running?");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell title="Reset password" subtitle="We'll email you a reset link.">
      {sent ? (
        <div className="rounded-[10px] border border-[rgba(34,197,94,0.4)] bg-[rgba(34,197,94,0.08)] px-4 py-4 text-sm text-[var(--success)]">
          If an account exists for <strong>{email}</strong>, a reset link is on its way. Check your inbox.
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <ErrorNote err={err} />
          <div>
            <Label>Email</Label>
            <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@studio.com" />
          </div>
          <Button type="submit" className="w-full" disabled={busy}>{busy ? "Sending…" : "Send reset link"}</Button>
          <p className="text-center text-sm">
            <Link href="/auth/login" className="cursor-pointer text-[var(--muted-fg)] hover:text-white">Back to login</Link>
          </p>
        </form>
      )}
    </Shell>
  );
}

export function ResetForm({ token }: { token: string }) {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const { api } = await import("@/lib/api");
      await api("/api/v1/auth/reset-password", { method: "POST", body: JSON.stringify({ token, password }), auth: false });
      setDone(true);
      setTimeout(() => router.push("/auth/login"), 2000);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Reset failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell title="Choose a new password" subtitle="Make it strong — min. 8 characters.">
      {done ? (
        <div className="rounded-[10px] border border-[rgba(34,197,94,0.4)] bg-[rgba(34,197,94,0.08)] px-4 py-4 text-sm text-[var(--success)]">
          Password updated. Redirecting you to login…
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <ErrorNote err={err} />
          <div>
            <Label>New password</Label>
            <Input type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
          </div>
          <Button type="submit" className="w-full" disabled={busy}>{busy ? "Updating…" : "Update password"}</Button>
        </form>
      )}
    </Shell>
  );
}
