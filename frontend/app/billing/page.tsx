"use client";
import { useEffect, useState } from "react";
import { Navbar } from "@/components/Navbar";
import { AuthGuard } from "@/components/chrome";
import { Button, Card, Spinner } from "@/components/ui";
import { api, fmtCredits, ApiError } from "@/lib/api";
import type { Plan } from "@/lib/types";

interface Txn {
  id: string;
  amount?: number;
  credits?: number;
  description?: string;
  created_at?: string;
  type?: string;
}

export default function BillingPage() {
  const [credits, setCredits] = useState<number | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [txns, setTxns] = useState<Txn[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api<{ credits: number }>("/api/v1/billing/credits").catch(() => null),
      api<Plan[]>("/api/v1/billing/plans").catch(() => []),
      api<Txn[]>("/api/v1/billing/transactions").catch(() => null),
    ]).then(([bal, ps, tx]) => {
      setCredits(bal?.credits ?? null);
      setPlans(Array.isArray(ps) ? ps : []);
      setTxns(tx);
    }).finally(() => setLoading(false));
  }, []);

  const checkout = async (plan: Plan) => {
    setBusy(plan.id);
    setMsg(null);
    try {
      const res = await api<{ checkout_url?: string; session_id?: string; stub?: boolean }>(
        "/api/v1/billing/checkout",
        { method: "POST", body: JSON.stringify({ plan: plan.id }) }
      );
      if (res?.checkout_url) {
        window.location.href = res.checkout_url;
      } else {
        // stub / test-mode session — refresh balance
        setMsg(
          res?.stub
            ? `Test checkout complete (session ${res.session_id ?? "n/a"}). Credits added.`
            : "Checkout session created. Complete payment to receive credits."
        );
        const bal = await api<{ credits: number }>("/api/v1/billing/credits").catch(() => null);
        if (bal) setCredits(bal.credits);
      }
    } catch (e) {
      setMsg(e instanceof ApiError ? `Checkout failed: ${e.message}` : "Checkout failed.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <AuthGuard>
      <div className="min-h-screen bg-black">
        <Navbar />
        <main className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
          <h1 className="font-display text-3xl font-bold">Billing & credits</h1>
          <p className="mt-1 text-[var(--muted-fg)]">1 credit = 1 minute of processed video. Failed jobs never consume credits.</p>

          {loading ? (
            <div className="flex justify-center py-20"><Spinner size={32} /></div>
          ) : (
            <>
              <Card className="mt-8 flex flex-wrap items-center justify-between gap-4 p-6">
                <div>
                  <p className="text-xs uppercase tracking-wider text-[var(--muted-fg)]">Current balance</p>
                  <p className="font-display text-5xl font-bold text-[var(--accent)]">{fmtCredits(credits)}</p>
                  <p className="mt-1 text-sm text-[var(--muted-fg)]">credits ≈ {credits != null ? Math.floor(credits) : "—"} minutes of video</p>
                </div>
                <div className="text-sm text-[var(--muted-fg)]">
                  <p>Analysis + planning + render of a 10-min video = 10 credits.</p>
                </div>
              </Card>

              {msg && <p className="mt-4 text-sm text-[var(--accent)]">{msg}</p>}

              <h2 className="mt-10 font-display text-xl font-bold">Top up</h2>
              {plans.length === 0 ? (
                <Card className="mt-4 p-5 text-sm text-[var(--muted-fg)]">
                  Plan catalog isn't available on this server yet. Plans are normally: Starter $19 / 120 credits, Creator $49 / 400 credits, Studio $149 / 1,500 credits.
                </Card>
              ) : (
                <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {plans.map((p) => (
                    <Card key={p.id} className="flex flex-col p-6">
                      <h3 className="font-display text-lg font-semibold">{p.name}</h3>
                      <div className="mt-2 flex items-baseline gap-2">
                        <span className="font-display text-4xl font-bold">${p.price ?? "—"}</span>
                        <span className="text-sm text-[var(--muted-fg)]">/ {fmtCredits(p.credits)} credits</span>
                      </div>
                      <Button className="mt-5 w-full" onClick={() => checkout(p)} disabled={busy === p.id}>
                        {busy === p.id ? "Starting checkout…" : `Buy ${p.name}`}
                      </Button>
                    </Card>
                  ))}
                </div>
              )}

              <h2 className="mt-10 font-display text-xl font-bold">Transaction history</h2>
              {txns === null ? (
                <p className="mt-3 text-sm text-[var(--muted-fg)]">Transaction history isn't available on this server yet.</p>
              ) : txns.length === 0 ? (
                <Card className="mt-4 p-5 text-sm text-[var(--muted-fg)]">No transactions yet.</Card>
              ) : (
                <Card className="mt-4 divide-y divide-[var(--border)]">
                  {txns.map((t) => (
                    <div key={t.id} className="flex items-center justify-between px-5 py-3 text-sm">
                      <div>
                        <p className="font-semibold">{t.description ?? t.type ?? "Transaction"}</p>
                        <p className="text-xs text-[var(--muted-fg)]">{t.created_at ? new Date(t.created_at).toLocaleString() : ""}</p>
                      </div>
                      <span className={`font-mono font-semibold ${((t.credits ?? 0) >= 0) ? "text-[var(--success)]" : "text-[var(--destructive)]"}`}>
                        {(t.credits ?? 0) >= 0 ? "+" : ""}{t.credits ?? t.amount ?? "—"}
                      </span>
                    </div>
                  ))}
                </Card>
              )}
            </>
          )}
        </main>
      </div>
    </AuthGuard>
  );
}
