"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, useReducedMotion } from "framer-motion";
import { Navbar } from "@/components/Navbar";
import { AuthGuard } from "@/components/chrome";
import { Button, Card, Input, EmptyState } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { Template, Project } from "@/lib/types";

const FALLBACK: Template[] = [
  { id: "vlog", name: "Vlog Energy", category: "Vlog", description: "Punchy cuts, bold kinetic text, emoji reactions.", accent: "#e11d48" },
  { id: "podcast", name: "Podcast Clean", category: "Podcast", description: "Calm pacing, lower thirds, minimal captions.", accent: "#6366f1" },
  { id: "course", name: "Course Pro", category: "Course", description: "Chapter callouts, stat popups, breathing room.", accent: "#0ea5e9" },
  { id: "ugc-ad", name: "UGC Ad", category: "Ad/UGC", description: "Hook-first, captions top, CTA end card.", accent: "#f59e0b" },
  { id: "testimonial", name: "Testimonial", category: "Testimonial", description: "Quote cards, soft fades, trust badges.", accent: "#22c55e" },
  { id: "fitness", name: "Fitness Hype", category: "Fitness", description: "High-energy cuts, timer graphics, beat sync.", accent: "#ef4444" },
  { id: "talking-head", name: "Talking Head+", category: "Vlog", description: "Jump cuts + punch-ins on emphasis words.", accent: "#a855f7" },
  { id: "interview", name: "Interview Duo", category: "Podcast", description: "Speaker labels, split reactions, clean lower thirds.", accent: "#14b8a6" },
  { id: "product-demo", name: "Product Demo", category: "Ad/UGC", description: "Zoom callouts, feature bullets, price pops.", accent: "#f97316" },
  { id: "webinar", name: "Webinar Cut", category: "Course", description: "Dead-air removal, key-point slides text.", accent: "#3b82f6" },
  { id: "shorts-pack", name: "Shorts Pack", category: "Shorts", description: "Vertical-first, 4-word caption lines, progress bar.", accent: "#ec4899" },
  { id: "documentary", name: "Docu Calm", category: "Course", description: "Slow crossfades, elegant serif titles.", accent: "#94a3b8" },
  { id: "sales-video", name: "Sales Letter", category: "Ad/UGC", description: "Urgency graphics, guarantee badges, CTA loops.", accent: "#eab308" },
  { id: "gaming", name: "Gaming Hype", category: "Vlog", description: "Glitch cuts, meme captions, loud stingers.", accent: "#8b5cf6" },
  { id: "cooking", name: "Cooking Show", category: "Vlog", description: "Ingredient callouts, timer overlays, top-down safe.", accent: "#fb7185" },
  { id: "real-estate", name: "Real Estate", category: "Ad/UGC", description: "Cinematic pans text, price stats, tour chapters.", accent: "#06b6d4" },
  { id: "saas-demo", name: "SaaS Demo", category: "Ad/UGC", description: "Cursor zoom, feature labels, clean transitions.", accent: "#6366f1" },
  { id: "motivation", name: "Motivation", category: "Shorts", description: "Epic quotes, beat-matched punch-ins.", accent: "#f43f5e" },
  { id: "news-recap", name: "News Recap", category: "Podcast", description: "Ticker lower third, source cards, fast chapters.", accent: "#38bdf8" },
  { id: "tutorial", name: "Tutorial Step", category: "Course", description: "Numbered steps, checklist graphics, recap cards.", accent: "#4ade80" },
];

export default function TemplatesPage() {
  const reduce = useReducedMotion() ?? false;
  const router = useRouter();
  const [templates, setTemplates] = useState<Template[]>(FALLBACK);
  const [fromApi, setFromApi] = useState(false);
  const [query, setQuery] = useState("");
  const [cat, setCat] = useState("All");
  const [projects, setProjects] = useState<Project[]>([]);
  const [applying, setApplying] = useState<string | null>(null);
  const [pickFor, setPickFor] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    api<Template[]>("/api/v1/templates")
      .then((t) => {
        if (Array.isArray(t) && t.length) {
          setTemplates(t);
          setFromApi(true);
        }
      })
      .catch(() => {});
    api<Project[]>("/api/v1/projects").then((p) => setProjects(Array.isArray(p) ? p : [])).catch(() => {});
  }, []);

  const cats = ["All", ...Array.from(new Set(templates.map((t) => t.category ?? "Other")))];
  const filtered = templates.filter(
    (t) =>
      (cat === "All" || (t.category ?? "Other") === cat) &&
      (!query || t.name.toLowerCase().includes(query.toLowerCase()))
  );

  const apply = async (templateId: string, projectId: string) => {
    setApplying(templateId);
    setMsg(null);
    try {
      await api(`/api/v1/projects/${projectId}/apply-template`, {
        method: "POST",
        body: JSON.stringify({ template_id: templateId }),
      });
      setMsg("Template applied — opening the editor…");
      setTimeout(() => router.push(`/project/${projectId}/edit`), 800);
    } catch (e) {
      setMsg(e instanceof ApiError ? `Apply failed: ${e.message}` : "Apply failed.");
    } finally {
      setApplying(null);
      setPickFor(null);
    }
  };

  return (
    <AuthGuard>
      <div className="min-h-screen bg-black">
        <Navbar />
        <main className="mx-auto max-w-7xl px-4 py-10 sm:px-6">
          <div className="mb-2 flex items-center justify-between">
            <div>
              <h1 className="font-display text-3xl font-bold">Style templates</h1>
              <p className="mt-1 text-[var(--muted-fg)]">
                One click re-skins every graphic in a project.{" "}
                {!fromApi && <span className="text-xs">(showing built-in catalog — live list unavailable)</span>}
              </p>
            </div>
          </div>
          {msg && <p className="mb-4 text-sm text-[var(--accent)]">{msg}</p>}
          <div className="mb-8 flex flex-wrap gap-2">
            <Input placeholder="Search templates…" value={query} onChange={(e) => setQuery(e.target.value)} className="!w-52" />
            {cats.map((c) => (
              <button
                key={c}
                onClick={() => setCat(c)}
                className={`cursor-pointer rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                  cat === c ? "text-white" : "bg-[var(--muted-bg)] text-[var(--muted-fg)] hover:text-white"
                }`}
                style={cat === c ? { background: "var(--brand-gradient)" } : undefined}
              >
                {c}
              </button>
            ))}
          </div>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {filtered.map((t, i) => (
              <motion.div
                key={t.id}
                initial={reduce ? { opacity: 1 } : { opacity: 0, scale: 0.94, y: 14 }}
                whileInView={{ opacity: 1, scale: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.35, delay: Math.min(i, 8) * 0.04 }}
              >
                <Card className="flex h-full flex-col overflow-hidden transition-colors hover:border-[var(--accent)]">
                  <div className="flex h-28 items-center justify-center" style={{ background: `linear-gradient(135deg, ${t.accent ?? "#e11d48"}33, transparent)` }}>
                    <span className="font-display text-2xl font-bold" style={{ color: t.accent ?? "#e11d48" }}>
                      {t.name.split(" ").map((w) => w[0]).slice(0, 2).join("")}
                    </span>
                  </div>
                  <div className="flex flex-1 flex-col p-4">
                    <p className="text-[11px] font-bold uppercase tracking-wider text-[var(--muted-fg)]">{t.category}</p>
                    <h3 className="mt-1 font-display font-semibold">{t.name}</h3>
                    <p className="mt-1 flex-1 text-sm text-[var(--muted-fg)]">{t.description}</p>
                    {pickFor === t.id ? (
                      <div className="mt-3 space-y-2">
                        <p className="text-xs text-[var(--muted-fg)]">Apply to project:</p>
                        <div className="max-h-32 space-y-1 overflow-y-auto slim-scroll">
                          {projects.length === 0 && <p className="text-xs text-[var(--muted-fg)]">No projects yet.</p>}
                          {projects.map((p) => (
                            <button
                              key={p.id}
                              onClick={() => apply(t.id, p.id)}
                              disabled={applying === t.id}
                              className="block w-full cursor-pointer truncate rounded-lg bg-[var(--muted-bg)] px-3 py-1.5 text-left text-sm hover:bg-[var(--border-strong)] disabled:opacity-50"
                            >
                              {applying === t.id ? "Applying…" : p.name}
                            </button>
                          ))}
                        </div>
                        <Button variant="ghost" size="sm" onClick={() => setPickFor(null)}>Cancel</Button>
                      </div>
                    ) : (
                      <Button variant="soft" size="sm" className="mt-3 w-full" onClick={() => setPickFor(t.id)}>
                        Apply to project
                      </Button>
                    )}
                  </div>
                </Card>
              </motion.div>
            ))}
          </div>
          {filtered.length === 0 && <EmptyState title="No templates match" hint="Try a different search or category." />}
        </main>
      </div>
    </AuthGuard>
  );
}
