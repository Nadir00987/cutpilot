"use client";
import { useEffect, useRef, useState } from "react";
import { Navbar } from "@/components/Navbar";
import { AuthGuard } from "@/components/chrome";
import { Button, Card, Input, Select, Label, Spinner } from "@/components/ui";
import { api, apiBase, ApiError } from "@/lib/api";

interface BrandKit {
  primary_color?: string;
  secondary_color?: string;
  font_heading?: string;
  font_body?: string;
  logo_url?: string;
  intro_enabled?: boolean;
  outro_enabled?: boolean;
  watermark_enabled?: boolean;
}

const FONTS = ["Space Grotesk", "Inter", "Montserrat", "Bebas Neue", "Playfair Display", "Roboto", "Oswald", "Poppins"];

export default function BrandKitPage() {
  const [kit, setKit] = useState<BrandKit | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api<BrandKit>("/api/v1/brand-kit")
      .then(setKit)
      .catch(() => setKit({}))
      .finally(() => setLoading(false));
  }, []);

  const patch = (p: Partial<BrandKit>) => setKit((k) => ({ ...(k ?? {}), ...p }));

  const save = async () => {
    if (!kit) return;
    setSaving(true);
    setMsg(null);
    try {
      const res = await api<BrandKit>("/api/v1/brand-kit", { method: "PUT", body: JSON.stringify(kit) });
      setKit(res);
      setMsg("Brand kit saved — it now applies to all new renders.");
    } catch (e) {
      setMsg(e instanceof ApiError ? `Save failed: ${e.message}` : "Save failed.");
    } finally {
      setSaving(false);
    }
  };

  const uploadLogo = async (f: File) => {
    setUploading(true);
    setMsg(null);
    try {
      const fd = new FormData();
      fd.append("logo", f);
      const res = await api<{ logo_url: string }>("/api/v1/brand-kit/logo", { method: "POST", body: fd });
      patch({ logo_url: res.logo_url });
      setMsg("Logo uploaded.");
    } catch (e) {
      setMsg(e instanceof ApiError ? `Upload failed: ${e.message}` : "Upload failed.");
    } finally {
      setUploading(false);
    }
  };

  const logoSrc = kit?.logo_url
    ? (kit.logo_url.startsWith("http") ? kit.logo_url : `${apiBase}${kit.logo_url}`)
    : null;

  const Toggle = ({ label, desc, value, onChange }: { label: string; desc: string; value?: boolean; onChange: (v: boolean) => void }) => (
    <div className="flex items-center justify-between gap-4 rounded-[var(--radius-sm)] border border-[var(--border)] bg-[var(--surface)] p-4">
      <div>
        <p className="font-semibold">{label}</p>
        <p className="text-sm text-[var(--muted-fg)]">{desc}</p>
      </div>
      <button
        role="switch"
        aria-checked={!!value}
        onClick={() => onChange(!value)}
        className="relative h-7 w-12 shrink-0 cursor-pointer rounded-full transition-colors duration-150"
        style={{ background: value ? "var(--accent)" : "var(--border-strong)" }}
      >
        <span
          className="absolute top-1 h-5 w-5 rounded-full bg-white transition-all duration-150"
          style={{ left: value ? 26 : 4 }}
        />
      </button>
    </div>
  );

  return (
    <AuthGuard>
      <div className="min-h-screen bg-black">
        <Navbar />
        <main className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
          <h1 className="font-display text-3xl font-bold">Brand kit</h1>
          <p className="mt-1 text-[var(--muted-fg)]">Set it once — logo, colors and fonts auto-apply to every graphic, intro, outro and watermark.</p>

          {loading ? (
            <div className="flex justify-center py-20"><Spinner size={32} /></div>
          ) : (
            <div className="mt-8 grid gap-8 lg:grid-cols-2">
              <div className="space-y-6">
                <Card className="p-6">
                  <h2 className="font-display text-lg font-semibold">Logo</h2>
                  <div className="mt-4 flex items-center gap-4">
                    <div className="flex h-20 w-20 items-center justify-center overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)]">
                      {logoSrc ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={logoSrc} alt="Brand logo" className="max-h-full max-w-full object-contain" />
                      ) : (
                        <span className="text-xs text-[var(--muted-fg)]">No logo</span>
                      )}
                    </div>
                    <div>
                      <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadLogo(f); e.target.value = ""; }} />
                      <Button variant="outline" size="sm" onClick={() => fileRef.current?.click()} disabled={uploading}>
                        {uploading ? "Uploading…" : "Upload logo"}
                      </Button>
                      <p className="mt-1.5 text-xs text-[var(--muted-fg)]">PNG with transparency works best.</p>
                    </div>
                  </div>
                </Card>

                <Card className="p-6">
                  <h2 className="font-display text-lg font-semibold">Colors</h2>
                  <div className="mt-4 grid gap-4 sm:grid-cols-2">
                    <div>
                      <Label>Primary (CTAs, progress, accents)</Label>
                      <div className="flex items-center gap-3">
                        <input
                          type="color"
                          value={kit?.primary_color ?? "#e11d48"}
                          onChange={(e) => patch({ primary_color: e.target.value })}
                          className="h-11 w-16 cursor-pointer rounded-lg border border-[var(--border)] bg-transparent"
                        />
                        <Input value={kit?.primary_color ?? "#e11d48"} onChange={(e) => patch({ primary_color: e.target.value })} className="font-mono" />
                      </div>
                    </div>
                    <div>
                      <Label>Secondary</Label>
                      <div className="flex items-center gap-3">
                        <input
                          type="color"
                          value={kit?.secondary_color ?? "#6366f1"}
                          onChange={(e) => patch({ secondary_color: e.target.value })}
                          className="h-11 w-16 cursor-pointer rounded-lg border border-[var(--border)] bg-transparent"
                        />
                        <Input value={kit?.secondary_color ?? "#6366f1"} onChange={(e) => patch({ secondary_color: e.target.value })} className="font-mono" />
                      </div>
                    </div>
                  </div>
                </Card>

                <Card className="p-6">
                  <h2 className="font-display text-lg font-semibold">Fonts</h2>
                  <div className="mt-4 grid gap-4 sm:grid-cols-2">
                    <div>
                      <Label>Headings / kinetic text</Label>
                      <Select value={kit?.font_heading ?? "Space Grotesk"} onChange={(e) => patch({ font_heading: e.target.value })} className="w-full">
                        {FONTS.map((f) => <option key={f}>{f}</option>)}
                      </Select>
                    </div>
                    <div>
                      <Label>Body / captions</Label>
                      <Select value={kit?.font_body ?? "Inter"} onChange={(e) => patch({ font_body: e.target.value })} className="w-full">
                        {FONTS.map((f) => <option key={f}>{f}</option>)}
                      </Select>
                    </div>
                  </div>
                </Card>

                <div className="space-y-3">
                  <Toggle label="Branded intro" desc="2–3s animated intro built from your logo + colors." value={kit?.intro_enabled} onChange={(v) => patch({ intro_enabled: v })} />
                  <Toggle label="End card / outro" desc="Subscribe CTA end card on every export." value={kit?.outro_enabled} onChange={(v) => patch({ outro_enabled: v })} />
                  <Toggle label="Watermark" desc="Small logo bug in the corner of exports." value={kit?.watermark_enabled} onChange={(v) => patch({ watermark_enabled: v })} />
                </div>

                {msg && <p className="text-sm text-[var(--accent)]">{msg}</p>}
                <Button onClick={save} disabled={saving} size="lg" className="w-full sm:w-auto">
                  {saving ? "Saving…" : "Save brand kit"}
                </Button>
              </div>

              {/* live preview */}
              <div className="lg:sticky lg:top-24 lg:self-start">
                <h2 className="mb-3 font-display text-lg font-semibold">Live preview</h2>
                <Card className="overflow-hidden">
                  <div className="relative aspect-video bg-black">
                    <div className="absolute inset-0" style={{ background: `radial-gradient(ellipse 70% 60% at 50% 40%, ${kit?.primary_color ?? "#e11d48"}26, transparent 65%)` }} />
                    <div className="absolute left-[8%] top-[30%] k-slide-up">
                      <p className="font-display text-3xl font-bold text-white" style={{ fontFamily: kit?.font_heading }}>
                        Your headline here
                      </p>
                      <p className="mt-1 text-lg text-white/70" style={{ fontFamily: kit?.font_body }}>kinetic typography in your brand font</p>
                    </div>
                    <div className="absolute bottom-[18%] left-[8%]">
                      <div className="rounded-lg border-l-4 bg-black/75 px-4 py-2.5" style={{ borderColor: kit?.primary_color ?? "#e11d48" }}>
                        <p className="font-display font-bold text-white">Alex Creator</p>
                        <p className="text-sm text-white/70">Lower third — your colors</p>
                      </div>
                    </div>
                    {logoSrc && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={logoSrc} alt="" className="absolute right-4 top-4 h-10 object-contain opacity-90" />
                    )}
                    {kit?.watermark_enabled && !logoSrc && (
                      <span className="absolute bottom-3 right-4 text-xs font-bold text-white/40">YOUR LOGO</span>
                    )}
                    <div className="absolute inset-x-0 top-0 h-1.5" style={{ background: kit?.primary_color ?? "#e11d48" }} />
                    <div className="absolute inset-x-0 bottom-6 flex justify-center">
                      <span className="rounded-lg bg-black/70 px-4 py-1.5 text-lg font-semibold">
                        <span className="karaoke-word active">Brand</span> <span className="karaoke-word">captions</span>
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center justify-between p-4 text-sm text-[var(--muted-fg)]">
                    <span>Intro: {kit?.intro_enabled ? "on" : "off"} · Outro: {kit?.outro_enabled ? "on" : "off"} · Watermark: {kit?.watermark_enabled ? "on" : "off"}</span>
                  </div>
                </Card>
              </div>
            </div>
          )}
        </main>
      </div>
    </AuthGuard>
  );
}
