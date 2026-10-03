"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { AuthGuard } from "@/components/chrome";
import { Button, Card, Input, Select, Label, Spinner, EmptyState } from "@/components/ui";
import { api, apiOptional, apiBase, fmtTime, ApiError, getAccessToken } from "@/lib/api";
import type { EditPlan, KeptSpan, Graphic, CaptionSegment, BrollClip, Project, Analysis } from "@/lib/types";
import { PreviewPlayer, type PlayerHandle } from "@/components/editor/PreviewPlayer";
import { Timeline, type Selection, type TLItem } from "@/components/editor/Timeline";
import {
  toEditedSpans, editedDuration, editToSource, sourceToEdit, spanAtEdit, uid, clamp,
} from "@/components/editor/timeMath";
import { demoPlan } from "@/components/editor/demoPlan";

interface Snapshot {
  cuts: KeptSpan[];
  graphics: Graphic[];
  captionsSegs: CaptionSegment[];
  broll: BrollClip[];
}

const TRACK_DEFS = [
  { key: "video", label: "Video", color: "var(--track-video)", height: 44 },
  { key: "broll", label: "B-roll", color: "var(--track-broll)", height: 30 },
  { key: "text", label: "Text", color: "var(--track-text)", height: 30 },
  { key: "captions", label: "Captions", color: "var(--track-captions)", height: 30 },
  { key: "audio", label: "Audio", color: "var(--track-audio)", height: 30 },
  { key: "music", label: "Music", color: "var(--track-music)", height: 30 },
  { key: "effects", label: "Effects", color: "var(--track-effects)", height: 30 },
];

function normalizeCuts(plan: EditPlan, duration: number): KeptSpan[] {
  if (plan.cuts && plan.cuts.length) {
    return plan.cuts.map((c, i) => ({
      id: c.id ?? uid("k"),
      start: c.start,
      end: c.end,
      speed: c.speed && c.speed > 0 ? c.speed : 1,
      label: c.label ?? `Clip ${i + 1}`,
    }));
  }
  const removed = (plan.removed ?? []).slice().sort((a, b) => a.start - b.start);
  const kept: KeptSpan[] = [];
  let cur = 0;
  removed.forEach((r, i) => {
    if (r.start > cur) kept.push({ id: uid("k"), start: cur, end: r.start, label: `Clip ${i + 1}` });
    cur = Math.max(cur, r.end);
  });
  if (cur < duration) kept.push({ id: uid("k"), start: cur, end: duration, label: `Clip ${kept.length + 1}` });
  if (!kept.length && duration > 0) kept.push({ id: uid("k"), start: 0, end: duration, label: "Clip 1" });
  return kept;
}

export default function EditorPage() {
  const params = useParams();
  const id = params.id as string;
  const router = useRouter();
  const playerRef = useRef<PlayerHandle>(null);

  const [project, setProject] = useState<Project | null>(null);
  const [plan, setPlan] = useState<EditPlan | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [srcUrl, setSrcUrl] = useState<string | null>(null);
  const srcUrlRef = useRef<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [demo, setDemo] = useState(false);

  const [playhead, setPlayhead] = useState(0);
  const [pxPerSec, setPxPerSec] = useState(40);
  const [selected, setSelected] = useState<Selection | null>(null);
  const [undoStack, setUndoStack] = useState<Snapshot[]>([]);
  const [redoStack, setRedoStack] = useState<Snapshot[]>([]);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [rerunOpen, setRerunOpen] = useState(false);
  const [versions, setVersions] = useState<{ version: number; created_at?: string }[]>([]);
  const [sideTab, setSideTab] = useState<"captions" | "graphics" | "clips" | "comments" | "versions">("captions");
  const [comments, setComments] = useState<{ id: string; timestamp?: number; text: string; author?: string }[] | null>(null);
  const [commentText, setCommentText] = useState("");
  const [editingWord, setEditingWord] = useState<string | null>(null); // "segId:wordIdx"
  const [wordDraft, setWordDraft] = useState("");

  const duration = useMemo(() => {
    const d = analysis?.duration ?? project?.duration ?? 0;
    if (d > 0) return d;
    const cuts = plan ? normalizeCuts(plan, 0) : [];
    return cuts.length ? Math.max(...cuts.map((c) => c.end)) : 60;
  }, [analysis, project, plan]);

  const kept = useMemo(() => (plan ? normalizeCuts(plan, duration) : []), [plan, duration]);
  const spans = useMemo(() => toEditedSpans(kept), [kept]);
  const editDur = editedDuration(spans);
  const graphics: Graphic[] = plan?.graphics ?? [];
  const capSegs: CaptionSegment[] = plan?.captions?.segments ?? [];
  const broll: BrollClip[] = plan?.broll ?? [];
  const brandColor = (plan?.brand?.primary_color as string) ?? "#e11d48";

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const p = await api<Project>(`/api/v1/projects/${id}`);
      setProject(p);
      const [pl, an] = await Promise.all([
        api<EditPlan>(`/api/v1/projects/${id}/plan`).catch(() => null),
        api<Analysis>(`/api/v1/projects/${id}/analysis`).catch(() => null),
      ]);
      setPlan(pl);
      setAnalysis(an);
      // Source media: the endpoint streams raw bytes and requires Bearer auth.
      // <video> tags can't send auth headers, so fetch as a blob and preview via an object URL.
      try {
        const token = getAccessToken();
        const res = await fetch(`${apiBase}/api/v1/projects/${id}/source`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (res.ok) {
          const blob = await res.blob();
          if (blob.size > 0) {
            if (srcUrlRef.current?.startsWith("blob:")) URL.revokeObjectURL(srcUrlRef.current);
            srcUrlRef.current = URL.createObjectURL(blob);
            setSrcUrl(srcUrlRef.current);
          }
        }
      } catch {
        /* preview stays empty */
      }
      const vs = await api<{ version: number; created_at?: string }[]>(`/api/v1/projects/${id}/plan/versions`).catch(() => []);
      setVersions(Array.isArray(vs) ? vs : []);
      const cm = await apiOptional<{ id: string; timestamp?: number; text: string; author?: string }[]>(
        `/api/v1/projects/${id}/comments`
      ).catch(() => null);
      setComments(cm);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not reach the API.");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  // Revoke the preview object URL when the page unmounts.
  useEffect(() => {
    return () => {
      if (srcUrlRef.current?.startsWith("blob:")) URL.revokeObjectURL(srcUrlRef.current);
      srcUrlRef.current = null;
    };
  }, []);

  const snapshot = useCallback((): Snapshot => ({
    cuts: kept.map((k) => ({ ...k })),
    graphics: graphics.map((g) => ({ ...g })),
    captionsSegs: capSegs.map((s) => ({ ...s, words: s.words.map((w) => ({ ...w })) })),
    broll: broll.map((b) => ({ ...b })),
  }), [kept, graphics, capSegs, broll]);

  const pushUndo = useCallback(() => {
    setUndoStack((u) => [...u.slice(-49), snapshot()]);
    setRedoStack([]);
  }, [snapshot]);

  const applySnapshot = useCallback((s: Snapshot) => {
    setPlan((p) => {
      if (!p) return p;
      return { ...p, cuts: s.cuts, graphics: s.graphics, broll: s.broll, captions: { ...(p.captions ?? {}), segments: s.captionsSegs } };
    });
  }, []);

  const undo = useCallback(() => {
    setUndoStack((u) => {
      if (!u.length) return u;
      const prev = u[u.length - 1];
      setRedoStack((r) => [...r, snapshot()]);
      applySnapshot(prev);
      return u.slice(0, -1);
    });
  }, [snapshot, applySnapshot]);

  const redo = useCallback(() => {
    setRedoStack((r) => {
      if (!r.length) return r;
      const next = r[r.length - 1];
      setUndoStack((u) => [...u.slice(-49), snapshot()]);
      applySnapshot(next);
      return r.slice(0, -1);
    });
  }, [snapshot, applySnapshot]);

  const updateCuts = useCallback((cuts: KeptSpan[]) => {
    pushUndo();
    setPlan((p) => (p ? { ...p, cuts } : p));
  }, [pushUndo]);

  const onTrimSpan = useCallback((spanId: string, edge: "l" | "r", newSource: number) => {
    const idx = kept.findIndex((k) => k.id === spanId);
    if (idx < 0) return;
    const next = kept.map((k) => ({ ...k }));
    const cur = next[idx];
    if (edge === "l") {
      const lo = idx > 0 ? next[idx - 1].end : 0;
      cur.start = clamp(newSource, lo, cur.end - 0.2);
    } else {
      const hi = idx < next.length - 1 ? next[idx + 1].start : Infinity;
      cur.end = clamp(newSource, cur.start + 0.2, hi);
    }
    // live trim — the undo snapshot was pushed once at gesture start (onEditStart)
    setPlan((p) => (p ? { ...p, cuts: next } : p));
  }, [kept]);

  const onReorderSpan = useCallback((spanId: string, toIndex: number) => {
    const from = kept.findIndex((k) => k.id === spanId);
    if (from < 0 || from === toIndex) return;
    const next = kept.map((k) => ({ ...k }));
    const [moved] = next.splice(from, 1);
    next.splice(clamp(toIndex, 0, next.length), 0, moved);
    updateCuts(next);
  }, [kept, updateCuts]);

  const splitAtPlayhead = useCallback(() => {
    const span = spanAtEdit(spans, playhead);
    if (!span) return;
    const srcT = editToSource(spans, playhead);
    if (srcT == null) return;
    if (srcT - span.start < 0.25 || span.end - srcT < 0.25) return;
    const idx = kept.findIndex((k) => k.id === span.id);
    const next = kept.map((k) => ({ ...k }));
    const a = { ...next[idx], end: srcT, label: `${next[idx].label ?? "Clip"} A` };
    const b = { ...next[idx], id: uid("k"), start: srcT, label: `${next[idx].label ?? "Clip"} B` };
    next.splice(idx, 1, a, b);
    updateCuts(next);
    setSaveMsg("Split at playhead");
  }, [spans, playhead, kept, updateCuts]);

  const deleteSelected = useCallback(() => {
    if (!selected) return;
    pushUndo();
    if (selected.track === "video") {
      setPlan((p) => (p ? { ...p, cuts: kept.filter((k) => k.id !== selected.id) } : p));
    } else if (selected.track === "text") {
      setPlan((p) => (p ? { ...p, graphics: graphics.filter((g) => g.id !== selected.id) } : p));
    } else if (selected.track === "captions") {
      setPlan((p) => (p ? { ...p, captions: { ...(p.captions ?? {}), segments: capSegs.filter((s) => s.id !== selected.id) } } : p));
    } else if (selected.track === "broll") {
      setPlan((p) => (p ? { ...p, broll: broll.filter((b) => b.id !== selected.id) } : p));
    }
    setSelected(null);
    setSaveMsg("Deleted (ripple)");
  }, [selected, pushUndo, kept, graphics, capSegs, broll]);

  const setSpeed = useCallback((spanId: string, speed: number) => {
    const s = clamp(speed, 0.5, 2);
    updateCuts(kept.map((k) => (k.id === spanId ? { ...k, speed: s } : { ...k })));
  }, [kept, updateCuts]);

  const moveGraphic = useCallback((gid: string, x: number, y: number) => {
    setPlan((p) => (p ? { ...p, graphics: graphics.map((g) => (g.id === gid ? { ...g, x, y } : g)) } : p));
  }, [graphics]);

  const editWord = useCallback((segId: string, wIdx: number, text: string) => {
    pushUndo();
    setPlan((p) => {
      if (!p) return p;
      const segs = (p.captions?.segments ?? []).map((s) =>
        s.id === segId
          ? { ...s, words: s.words.map((w, i) => (i === wIdx ? { ...w, word: text } : w)) }
          : s
      );
      return { ...p, captions: { ...(p.captions ?? {}), segments: segs } };
    });
  }, [pushUndo]);

  const savePlan = useCallback(async () => {
    if (!plan) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      const res = await api<{ version?: number }>(`/api/v1/projects/${id}/plan`, {
        method: "PUT",
        body: JSON.stringify(plan),
      });
      const v = res?.version ?? (plan.version ?? 1) + 1;
      setPlan((p) => (p ? { ...p, version: v } : p));
      setSaveMsg(`Saved · v${v}`);
      const vs = await api<{ version: number; created_at?: string }[]>(`/api/v1/projects/${id}/plan/versions`).catch(() => []);
      setVersions(Array.isArray(vs) ? vs : []);
    } catch (e) {
      setSaveMsg(e instanceof ApiError ? `Save failed: ${e.message}` : "Save failed.");
    } finally {
      setSaving(false);
    }
  }, [plan, id]);

  const restoreVersion = useCallback(async (v: number) => {
    try {
      await api(`/api/v1/projects/${id}/plan/restore/${v}`, { method: "POST" });
      const pl = await api<EditPlan>(`/api/v1/projects/${id}/plan`);
      setPlan(pl);
      setUndoStack([]);
      setRedoStack([]);
      setSaveMsg(`Restored v${v}`);
    } catch (e) {
      setSaveMsg(e instanceof ApiError ? `Restore failed: ${e.message}` : "Restore failed.");
    }
  }, [id]);

  const seek = useCallback((t: number) => {
    setPlayhead(clamp(t, 0, editDur));
    playerRef.current?.requestSeek(t);
  }, [editDur]);

  // keyboard shortcuts
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable) return;
      if (e.code === "Space") { e.preventDefault(); playerRef.current?.toggle(); }
      else if (e.key === "s" || e.key === "S" || e.key === "c" || e.key === "C") { e.preventDefault(); splitAtPlayhead(); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); seek(playhead + (e.shiftKey ? -5 : -1 / 30)); }
      else if (e.key === "ArrowRight") { e.preventDefault(); seek(playhead + (e.shiftKey ? 5 : 1 / 30)); }
      else if ((e.key === "Delete" || e.key === "Backspace")) { e.preventDefault(); deleteSelected(); }
      else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && !e.shiftKey) { e.preventDefault(); undo(); }
      else if ((e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === "y" || (e.key.toLowerCase() === "z" && e.shiftKey))) { e.preventDefault(); redo(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [splitAtPlayhead, deleteSelected, undo, redo, seek, playhead]);

  const postComment = async () => {
    if (!commentText.trim()) return;
    try {
      const c = await api<{ id: string; timestamp?: number; text: string; author?: string }>(
        `/api/v1/projects/${id}/comments`,
        { method: "POST", body: JSON.stringify({ timestamp: Math.round(playhead * 10) / 10, text: commentText }) }
      );
      setComments((cs) => (cs ? [...cs, c] : [c]));
      setCommentText("");
    } catch (e) {
      setSaveMsg(e instanceof ApiError ? `Comment failed: ${e.message}` : "Comment failed.");
    }
  };

  // timeline track items
  const trackItems = useMemo(() => {
    const mapT = (s: number, e: number) => {
      const a = sourceToEdit(spans, s);
      const b = sourceToEdit(spans, e - 0.001);
      return a != null && b != null ? { eStart: a, eEnd: Math.max(b, a + 0.05) } : null;
    };
    type ItemIn = { id: string; start: number; end: number; label?: string; text?: string; type?: string; keyword?: string; words?: { word: string }[] };
    const items = (list: ItemIn[], labelOf: (x: ItemIn) => string | undefined): TLItem[] =>
      list.flatMap((x) => {
        const m = mapT(x.start, x.end);
        return m ? [{ id: x.id, eStart: m.eStart, eEnd: m.eEnd, label: labelOf(x) ?? "", color: "" }] : [];
      });
    return [
      {
        ...TRACK_DEFS[0],
        items: spans.map((s) => ({ id: s.id, eStart: s.editStart, eEnd: s.editEnd, label: `${s.label ?? "Clip"}${s.speed && s.speed !== 1 ? ` · ${s.speed}x` : ""}`, color: TRACK_DEFS[0].color })),
      },
      {
        ...TRACK_DEFS[1],
        items: items(broll, (b) => b.label ?? b.keyword ?? "B-roll").map((i) => ({ ...i, color: TRACK_DEFS[1].color })),
      },
      {
        ...TRACK_DEFS[2],
        items: items(graphics.filter((g) => g.type !== "progress" && g.type !== "punch-in"), (g) => g.text ?? g.type).map((i) => ({ ...i, color: TRACK_DEFS[2].color })),
      },
      {
        ...TRACK_DEFS[3],
        items: items(capSegs, (s) => (s.words ?? []).slice(0, 4).map((w) => w.word).join(" ")).map((i) => ({ ...i, color: TRACK_DEFS[3].color })),
      },
      {
        ...TRACK_DEFS[4],
        items: spans.map((s) => ({ id: `a_${s.id}`, eStart: s.editStart, eEnd: s.editEnd, label: "Voice", color: TRACK_DEFS[4].color })),
      },
      {
        ...TRACK_DEFS[5],
        items: plan?.music?.track ? [{ id: "music", eStart: 0, eEnd: editDur, label: plan.music.track, color: TRACK_DEFS[5].color }] : [],
      },
      {
        ...TRACK_DEFS[6],
        items: items(graphics.filter((g) => g.type === "punch-in"), () => "Punch-in").map((i) => ({ ...i, color: TRACK_DEFS[6].color })),
      },
    ];
  }, [spans, broll, graphics, capSegs, plan, editDur]);

  const selectedSpan = selected?.track === "video" ? kept.find((k) => k.id === selected.id) ?? null : null;

  if (loading) {
    return (
      <AuthGuard>
        <div className="flex min-h-screen items-center justify-center bg-black"><Spinner size={36} /></div>
      </AuthGuard>
    );
  }

  return (
    <AuthGuard>
      <div className="flex min-h-screen flex-col bg-black">
        {/* editor chrome */}
        <header className="z-40 border-b border-[var(--border)] bg-[rgba(0,0,0,0.9)] backdrop-blur-xl">
          <div className="flex flex-wrap items-center gap-2 px-4 py-3">
            <Link href="/dashboard" className="cursor-pointer text-sm text-[var(--muted-fg)] hover:text-white">← Projects</Link>
            <span className="mx-1 text-[var(--border-strong)]">|</span>
            <span className="font-display font-semibold">{project?.name ?? "Untitled project"}</span>
            {plan && <span className="rounded-full bg-[var(--muted-bg)] px-2.5 py-0.5 text-xs text-[var(--muted-fg)]">v{plan.version ?? 1}</span>}
            {demo && <span className="rounded-full bg-[var(--accent-soft)] px-2.5 py-0.5 text-xs font-semibold text-[var(--accent)]">DEMO</span>}
            <div className="ml-auto flex flex-wrap items-center gap-2">
              {saveMsg && <span className="text-xs text-[var(--muted-fg)]">{saveMsg}</span>}
              <Button variant="ghost" size="sm" onClick={undo} disabled={!undoStack.length} title="Undo (Ctrl+Z)">Undo</Button>
              <Button variant="ghost" size="sm" onClick={redo} disabled={!redoStack.length} title="Redo (Ctrl+Y)">Redo</Button>
              <Button variant="outline" size="sm" onClick={() => setRerunOpen(true)} disabled={!plan}>Re-run AI</Button>
              <Button variant="soft" size="sm" onClick={savePlan} disabled={!plan || saving}>{saving ? "Saving…" : "Save"}</Button>
              <Button size="sm" onClick={() => router.push(`/project/${id}/export`)}>Export →</Button>
            </div>
          </div>
        </header>

        {err && !plan ? (
          <main className="mx-auto w-full max-w-3xl px-4 py-16">
            <EmptyState
              title="Couldn't load this project"
              hint={err}
              action={
                <div className="flex gap-2">
                  <Button onClick={load}>Retry</Button>
                  <Button variant="outline" onClick={() => { setPlan(demoPlan()); setDemo(true); setErr(null); }}>
                    Explore with demo footage
                  </Button>
                </div>
              }
            />
          </main>
        ) : !plan ? (
          <main className="mx-auto w-full max-w-3xl px-4 py-16">
            <EmptyState
              title="No edit plan yet"
              hint="This project hasn't been analyzed. Run the AI analysis first, or explore the editor with a demo plan."
              action={
                <div className="flex gap-2">
                  <Link href={`/project/${id}/analyze`}><Button>Go to analysis</Button></Link>
                  <Button variant="outline" onClick={() => { setPlan(demoPlan()); setDemo(true); }}>
                    Load demo project
                  </Button>
                </div>
              }
            />
          </main>
        ) : (
          <main className="flex flex-1 flex-col gap-4 p-4 lg:flex-row">
            {/* left: preview + timeline */}
            <div className="flex min-w-0 flex-1 flex-col gap-4">
              <div className="mx-auto w-full max-w-4xl">
                <PreviewPlayer
                  ref={playerRef}
                  src={srcUrl}
                  spans={spans}
                  graphics={graphics}
                  captions={capSegs}
                  captionPosition={plan.captions?.position}
                  brandColor={brandColor}
                  onTime={setPlayhead}
                  onGraphicMove={moveGraphic}
                  onEditStart={pushUndo}
                />
                <div className="mt-2 flex items-center justify-between text-sm text-[var(--muted-fg)]">
                  <span className="font-mono">{fmtTime(playhead)} / {fmtTime(editDur)}</span>
                  <span className="hidden text-xs sm:inline">Space play · S split · C cut · ←/→ frame · Del remove · Ctrl+Z undo · drag edges to trim</span>
                  <div className="flex items-center gap-2">
                    <Button variant="ghost" size="sm" onClick={() => playerRef.current?.toggle()}>Play/Pause</Button>
                    <Button variant="ghost" size="sm" onClick={splitAtPlayhead}>Split (S)</Button>
                  </div>
                </div>
              </div>

              <div>
                <div className="mb-2 flex items-center gap-3">
                  <span className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-fg)]">Timeline</span>
                  <input
                    type="range" min={8} max={160} value={pxPerSec}
                    onChange={(e) => setPxPerSec(Number(e.target.value))}
                    className="w-40 accent-[#e11d48]"
                    aria-label="Timeline zoom"
                  />
                  <span className="text-xs text-[var(--muted-fg)]">{pxPerSec}px/s</span>
                  {selectedSpan && (
                    <span className="ml-2 flex items-center gap-2 text-xs">
                      Speed:
                      <Select value={String(selectedSpan.speed ?? 1)} onChange={(e) => setSpeed(selectedSpan.id, Number(e.target.value))} className="!py-1">
                        {[0.5, 0.75, 1, 1.25, 1.5, 1.75, 2].map((s) => (
                          <option key={s} value={s}>{s}x</option>
                        ))}
                      </Select>
                      <Button variant="danger" size="sm" onClick={deleteSelected}>Delete clip</Button>
                    </span>
                  )}
                </div>
                <Timeline
                  spans={spans}
                  tracks={trackItems}
                  playhead={playhead}
                  pxPerSec={pxPerSec}
                  selected={selected}
                  onSelect={setSelected}
                  onSeek={seek}
                  onTrimSpan={onTrimSpan}
                  onReorderSpan={onReorderSpan}
                  onEditStart={pushUndo}
                  duration={editDur}
                />
              </div>
            </div>

            {/* right: side panel */}
            <aside className="w-full shrink-0 lg:w-96">
              <Card className="flex h-full max-h-[calc(100vh-140px)] flex-col overflow-hidden">
                <div className="flex border-b border-[var(--border)]">
                  {(["captions", "graphics", "clips", "comments", "versions"] as const).map((t) => (
                    <button
                      key={t}
                      onClick={() => setSideTab(t)}
                      className={`cursor-pointer flex-1 px-2 py-3 text-xs font-semibold capitalize transition-colors ${
                        sideTab === t ? "text-white border-b-2 border-[var(--accent)]" : "text-[var(--muted-fg)] hover:text-white"
                      }`}
                    >
                      {t}
                    </button>
                  ))}
                </div>
                <div className="slim-scroll flex-1 overflow-y-auto p-4">
                  {sideTab === "captions" && (
                    <div className="space-y-3">
                      <p className="text-xs text-[var(--muted-fg)]">Click any word to edit its text. Timing stays locked.</p>
                      {capSegs.length === 0 && <p className="text-sm text-[var(--muted-fg)]">No captions in this plan.</p>}
                      {capSegs.map((s) => (
                        <div key={s.id} className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3">
                          <p className="mb-1.5 font-mono text-[11px] text-[var(--muted-fg)]">{fmtTime(s.start)} → {fmtTime(s.end)}</p>
                          <p className="text-sm leading-relaxed">
                            {s.words.map((w, i) => {
                              const key = `${s.id}:${i}`;
                              return editingWord === key ? (
                                <input
                                  key={key}
                                  autoFocus
                                  value={wordDraft}
                                  onChange={(e) => setWordDraft(e.target.value)}
                                  onBlur={() => { if (wordDraft.trim()) editWord(s.id, i, wordDraft.trim()); setEditingWord(null); }}
                                  onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
                                  className="w-24 rounded border border-[var(--accent)] bg-black px-1 py-0.5 text-sm"
                                />
                              ) : (
                                <span
                                  key={key}
                                  onClick={() => { setEditingWord(key); setWordDraft(w.word); }}
                                  className={`cursor-pointer rounded px-0.5 hover:bg-[var(--accent-soft)] ${w.emphasis ? "font-bold text-[var(--accent)]" : ""}`}
                                  title="Click to edit"
                                >
                                  {w.word}{" "}
                                </span>
                              );
                            })}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                  {sideTab === "graphics" && (
                    <div className="space-y-2">
                      <p className="text-xs text-[var(--muted-fg)]">Tip: drag any graphic directly on the preview canvas to reposition it.</p>
                      {graphics.length === 0 && <p className="text-sm text-[var(--muted-fg)]">No graphics in this plan.</p>}
                      {graphics.map((g) => (
                        <div
                          key={g.id}
                          onClick={() => { setSelected({ track: "text", id: g.id }); const m = sourceToEdit(spans, g.start); if (m != null) seek(m); }}
                          className={`cursor-pointer rounded-lg border p-3 text-sm transition-colors ${selected?.id === g.id ? "border-[var(--accent)]" : "border-[var(--border)] bg-[var(--surface)] hover:border-[var(--border-strong)]"}`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-semibold capitalize">{g.type.replace("-", " ")}</span>
                            <span className="font-mono text-[11px] text-[var(--muted-fg)]">{fmtTime(g.start)}→{fmtTime(g.end)}</span>
                          </div>
                          {g.text && <p className="mt-1 text-[var(--muted-fg)]">{g.text}</p>}
                          {g.reason && <p className="mt-1 text-xs italic text-[var(--faint-fg)]">AI: {g.reason}</p>}
                          <div className="mt-2 flex gap-2">
                            <Input
                              value={g.text ?? ""}
                              onChange={(e) => {
                                pushUndo();
                                setPlan((p) => (p ? { ...p, graphics: graphics.map((x) => (x.id === g.id ? { ...x, text: e.target.value } : x)) } : p));
                              }}
                              onClick={(e) => e.stopPropagation()}
                              className="!py-1 text-xs"
                              placeholder="Graphic text"
                            />
                            <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); setSelected({ track: "text", id: g.id }); deleteSelected(); }}>✕</Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                  {sideTab === "clips" && (
                    <div className="space-y-2">
                      {kept.map((k, i) => (
                        <div
                          key={k.id}
                          onClick={() => { setSelected({ track: "video", id: k.id }); seek(spans[i]?.editStart ?? 0); }}
                          className={`cursor-pointer rounded-lg border p-3 text-sm ${selected?.id === k.id ? "border-[var(--accent)]" : "border-[var(--border)] bg-[var(--surface)]"}`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-semibold">{k.label ?? `Clip ${i + 1}`}</span>
                            <span className="font-mono text-[11px] text-[var(--muted-fg)]">{fmtTime(k.start)}→{fmtTime(k.end)}</span>
                          </div>
                          <div className="mt-2 flex items-center gap-2 text-xs text-[var(--muted-fg)]">
                            Speed
                            <Select value={String(k.speed ?? 1)} onChange={(e) => setSpeed(k.id, Number(e.target.value))} className="!py-1">
                              {[0.5, 0.75, 1, 1.25, 1.5, 1.75, 2].map((s) => <option key={s} value={s}>{s}x</option>)}
                            </Select>
                            <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); setSelected({ track: "video", id: k.id }); deleteSelected(); }}>Delete</Button>
                          </div>
                        </div>
                      ))}
                      {plan.reasons && (
                        <div className="mt-4">
                          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--muted-fg)]">Why the AI cut what it cut</p>
                          {Object.entries(plan.reasons).map(([k, v]) => (
                            <p key={k} className="mb-1.5 text-xs text-[var(--muted-fg)]"><span className="font-mono text-white/70">{k}:</span> {String(v)}</p>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                  {sideTab === "comments" && (
                    <div className="space-y-3">
                      {comments === null ? (
                        <p className="text-sm text-[var(--muted-fg)]">Comments aren't available on this server yet (team features by Worker E).</p>
                      ) : (
                        <>
                          {comments.length === 0 && <p className="text-sm text-[var(--muted-fg)]">No comments yet. Pin one to the current playhead.</p>}
                          {comments.map((c) => (
                            <div key={c.id} className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3 text-sm">
                              <div className="mb-1 flex items-center justify-between text-xs text-[var(--muted-fg)]">
                                <span className="font-semibold text-white/80">{c.author ?? "Teammate"}</span>
                                {c.timestamp != null && (
                                  <button onClick={() => seek(c.timestamp!)} className="cursor-pointer font-mono text-[var(--accent)] hover:underline">
                                    {fmtTime(c.timestamp)}
                                  </button>
                                )}
                              </div>
                              <p>{c.text}</p>
                            </div>
                          ))}
                          <div className="flex gap-2">
                            <Input value={commentText} onChange={(e) => setCommentText(e.target.value)} placeholder={`Comment @ ${fmtTime(playhead)}…`} />
                            <Button size="sm" onClick={postComment}>Post</Button>
                          </div>
                        </>
                      )}
                    </div>
                  )}
                  {sideTab === "versions" && (
                    <div className="space-y-2">
                      <p className="text-xs text-[var(--muted-fg)]">Every save creates a new version. Restore any of them with one click.</p>
                      {versions.length === 0 && <p className="text-sm text-[var(--muted-fg)]">No saved versions yet — hit Save to create v{(plan.version ?? 1) + 1}.</p>}
                      {versions.map((v) => (
                        <div key={v.version} className="flex items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3 text-sm">
                          <span className="font-semibold">v{v.version}</span>
                          <span className="text-xs text-[var(--muted-fg)]">{v.created_at ? new Date(v.created_at).toLocaleString() : ""}</span>
                          <Button variant="outline" size="sm" onClick={() => restoreVersion(v.version)}>Restore</Button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </Card>
            </aside>
          </main>
        )}

        {/* Re-run AI modal */}
        {rerunOpen && <RerunModal id={id} onClose={() => setRerunOpen(false)} onDone={(p) => { setPlan(p); setUndoStack([]); setRedoStack([]); setRerunOpen(false); }} />}
      </div>
    </AuthGuard>
  );
}

function RerunModal({ id, onClose, onDone }: { id: string; onClose: () => void; onDone: (p: EditPlan) => void }) {
  const [pacing, setPacing] = useState("balanced");
  const [captionStyle, setCaptionStyle] = useState("hormozi");
  const [density, setDensity] = useState("medium");
  const [tone, setTone] = useState("energetic");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setErr(null);
    try {
      const p = await api<EditPlan>(`/api/v1/projects/${id}/plan`, {
        method: "POST",
        body: JSON.stringify({ pacing, caption_style: captionStyle, graphics_density: density, tone }),
      });
      onDone(p);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Re-run failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm" onClick={onClose}>
      <Card className="w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
        <h2 className="font-display text-xl font-bold">Re-run AI edit</h2>
        <p className="mt-1 text-sm text-[var(--muted-fg)]">Regenerate the edit plan with different style settings. Your footage stays uploaded.</p>
        <div className="mt-5 space-y-4">
          <div><Label>Pacing</Label>
            <Select value={pacing} onChange={(e) => setPacing(e.target.value)} className="w-full">
              <option value="fast">Fast — punchy, 2–3s shots</option>
              <option value="balanced">Balanced — 3–4s shots</option>
              <option value="calm">Calm — educational breathing room</option>
            </Select>
          </div>
          <div><Label>Caption style</Label>
            <Select value={captionStyle} onChange={(e) => setCaptionStyle(e.target.value)} className="w-full">
              <option value="hormozi">Hormozi — big bold</option>
              <option value="minimal">Minimal</option>
              <option value="karaoke">Karaoke</option>
              <option value="outline">Outline</option>
            </Select>
          </div>
          <div><Label>Graphics density</Label>
            <Select value={density} onChange={(e) => setDensity(e.target.value)} className="w-full">
              <option value="low">Low — only key moments</option>
              <option value="medium">Medium</option>
              <option value="high">High — maximum energy</option>
            </Select>
          </div>
          <div><Label>Tone</Label>
            <Select value={tone} onChange={(e) => setTone(e.target.value)} className="w-full">
              <option value="energetic">Energetic</option>
              <option value="professional">Professional</option>
              <option value="playful">Playful</option>
            </Select>
          </div>
        </div>
        {err && <p className="mt-3 text-sm text-[var(--destructive)]">{err}</p>}
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={run} disabled={busy}>{busy ? "Planning…" : "Regenerate plan"}</Button>
        </div>
      </Card>
    </div>
  );
}
