"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Spinner } from "./ui";

export function AuthGuard({ children, adminOnly = false }: { children: React.ReactNode; adminOnly?: boolean }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading) {
      if (!user) router.replace("/auth/login");
      else if (adminOnly && user.role !== "admin") router.replace("/dashboard");
    }
  }, [user, loading, router, adminOnly]);

  if (loading || !user || (adminOnly && user.role !== "admin")) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Spinner size={32} />
      </div>
    );
  }
  return <>{children}</>;
}

export function StatusBadge({ status }: { status?: string }) {
  const map: Record<string, { label: string; style: React.CSSProperties }> = {
    analyzing: { label: "Analyzing", style: { background: "rgba(245,158,11,0.15)", color: "var(--warning)" } },
    uploading: { label: "Uploading", style: { background: "rgba(56,189,248,0.15)", color: "var(--info)" } },
    ready: { label: "Ready", style: { background: "rgba(34,197,94,0.15)", color: "var(--success)" } },
    rendering: { label: "Rendering", style: { background: "rgba(99,102,241,0.18)", color: "#a5b4fc" } },
    done: { label: "Done", style: { background: "rgba(34,197,94,0.15)", color: "var(--success)" } },
    error: { label: "Error", style: { background: "rgba(239,68,68,0.15)", color: "var(--destructive)" } },
    queued: { label: "Queued", style: { background: "rgba(148,163,184,0.15)", color: "var(--muted-fg)" } },
    failed: { label: "Failed", style: { background: "rgba(239,68,68,0.15)", color: "var(--destructive)" } },
  };
  const s = map[status ?? ""] ?? { label: status ?? "—", style: { background: "var(--muted-bg)", color: "var(--muted-fg)" } };
  return (
    <span className="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold" style={s.style}>
      <span className="mr-1.5 h-1.5 w-1.5 rounded-full bg-current" />
      {s.label}
    </span>
  );
}
