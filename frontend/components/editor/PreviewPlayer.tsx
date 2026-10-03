"use client";
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import type { CaptionSegment, Graphic } from "@/lib/types";
import {
  EditedSpan, editedDuration, editToSource, sourceToEdit, nextKeptStart, spanAtSource, clamp,
} from "./timeMath";

export interface PlayerHandle {
  toggle: () => void;
  seekEdit: (t: number) => void;
  step: (delta: number) => void;
  isPlaying: () => boolean;
  requestSeek: (t: number) => void;
}

interface Props {
  src: string | null;
  spans: EditedSpan[];
  graphics: Graphic[];
  captions: CaptionSegment[];
  captionPosition?: "top" | "middle" | "bottom";
  brandColor?: string;
  onTime?: (t: number) => void;
  /** when provided, graphics become draggable on the canvas */
  onGraphicMove?: (id: string, x: number, y: number) => void;
  /** called once when a canvas graphic drag starts (for undo snapshots) */
  onEditStart?: () => void;
}

const KINETIC_CLASS: Record<string, string> = {
  "scale-pop": "k-scale-pop",
  "slide-up": "k-slide-up",
  typewriter: "k-typewriter",
  bounce: "k-bounce",
  "fade-blur": "k-fade-blur",
  pop: "k-scale-pop",
  slide: "k-slide-up",
};

interface MappedGraphic extends Graphic {
  eStart: number;
  eEnd: number;
}

function GraphicOverlay({
  g,
  brand,
  onMove,
  onEditStart,
}: {
  g: MappedGraphic;
  brand: string;
  onMove?: (id: string, x: number, y: number) => void;
  onEditStart?: () => void;
}) {
  const dragRef = useRef<HTMLDivElement>(null);
  const startDrag = (e: React.PointerEvent) => {
    if (!onMove) return;
    e.stopPropagation();
    e.preventDefault();
    onEditStart?.();
    const layer = (e.target as HTMLElement).closest("[data-canvas-layer]") as HTMLElement | null;
    if (!layer) return;
    const rect = layer.getBoundingClientRect();
    const move = (ev: PointerEvent) => {
      const x = ((ev.clientX - rect.left) / rect.width) * 100;
      const y = ((ev.clientY - rect.top) / rect.height) * 100;
      onMove(g.id, Math.round(Math.min(96, Math.max(4, x))), Math.round(Math.min(96, Math.max(4, y))));
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const cls = KINETIC_CLASS[g.style ?? ""] ?? "k-scale-pop";
  const centered: React.CSSProperties = {
    left: `${g.x ?? 50}%`,
    top: `${g.y ?? 50}%`,
    transform: "translate(-50%, -50%)",
  };
  const text = g.text ?? "";

  // outer position per graphic type
  const pos: React.CSSProperties =
    g.type === "lower-third"
      ? { left: "6%", bottom: "14%" }
      : g.type === "quote"
        ? { left: "50%", top: "38%", transform: "translate(-50%,-50%)" }
        : centered;

  const inner = (() => {
    switch (g.type) {
      case "lower-third":
        return (
          <div className="rounded-lg border-l-4 bg-black/75 px-4 py-2.5 backdrop-blur-sm" style={{ borderColor: brand }}>
            <p className="font-display text-lg font-bold text-white">{text.split("—")[0]}</p>
            {text.includes("—") && <p className="text-sm text-white/70">{text.split("—").slice(1).join("—")}</p>}
          </div>
        );
      case "callout":
        return (
          <div className="rounded-xl border-2 bg-black/60 px-4 py-2 font-display text-xl font-bold text-white backdrop-blur-sm" style={{ borderColor: brand }}>
            {text}
          </div>
        );
      case "stat":
        return (
          <div className="rounded-2xl px-6 py-4 text-center shadow-glow" style={{ background: "var(--brand-gradient)" }}>
            <p className="font-display text-3xl font-bold text-white">{text}</p>
          </div>
        );
      case "emoji":
        return <span className="text-6xl" aria-hidden>{text}</span>;
      case "quote":
        return (
          <p className="max-w-md rounded-xl bg-black/70 px-6 py-4 text-center font-display text-xl italic text-white backdrop-blur-sm">{text}</p>
        );
      case "subscribe":
        return (
          <div className="flex items-center gap-3 rounded-full bg-white px-6 py-3 shadow-xl">
            <span className="font-display text-lg font-bold text-black">{text || "Subscribe"}</span>
            <span className="rounded-full px-3 py-1 text-sm font-bold text-white" style={{ background: "var(--brand-gradient)" }}>SUB</span>
          </div>
        );
      case "progress":
        return null;
      case "kinetic":
      default:
        return (
          <p className="max-w-lg text-center font-display text-4xl font-bold leading-tight text-white drop-shadow-[0_2px_12px_rgba(0,0,0,0.9)]">
            {text}
          </p>
        );
    }
  })();

  if (inner === null) return null;
  return (
    <div
      ref={dragRef}
      className={`absolute ${cls} ${onMove ? "pointer-events-auto cursor-move" : ""}`}
      style={pos}
      onPointerDown={onMove ? startDrag : undefined}
      title={onMove ? "Drag to reposition" : undefined}
    >
      {inner}
    </div>
  );
}

export const PreviewPlayer = forwardRef<PlayerHandle, Props>(function PreviewPlayer(
  { src, spans, graphics, captions, captionPosition = "bottom", brandColor = "#e11d48", onTime, onGraphicMove, onEditStart },
  ref
) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const rafRef = useRef(0);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const dur = editedDuration(spans);
  const lastCb = useRef(0);
  const clockRef = useRef({ last: 0, t: 0 });
  const spansRef = useRef(spans);
  spansRef.current = spans;

  const mappedGraphics = useMemo<MappedGraphic[]>(() => {
    const out: MappedGraphic[] = [];
    for (const g of graphics) {
      const eStart = sourceToEdit(spans, g.start);
      const eEnd = sourceToEdit(spans, g.end - 0.001);
      if (eStart == null || eEnd == null) continue;
      out.push({ ...g, eStart, eEnd: Math.max(eEnd, eStart + 0.1) });
    }
    return out;
  }, [graphics, spans]);

  const mappedCaptions = useMemo(() => {
    const out: (CaptionSegment & { eStart: number; eEnd: number })[] = [];
    for (const s of captions) {
      const eStart = sourceToEdit(spans, s.start);
      const eEnd = sourceToEdit(spans, s.end - 0.001);
      if (eStart == null || eEnd == null) continue;
      const words = s.words
        .map((w) => {
          const ws = sourceToEdit(spans, w.start);
          const we = sourceToEdit(spans, w.end - 0.001);
          return ws == null || we == null ? null : { ...w, start: ws, end: we };
        })
        .filter((w): w is CaptionSegment["words"][number] => w !== null);
      out.push({ ...s, eStart, eEnd, words });
    }
    return out;
  }, [captions, spans]);

  const activeGraphics = mappedGraphics.filter((g) => t >= g.eStart && t < g.eEnd && g.type !== "progress");
  const showProgress = mappedGraphics.some((g) => g.type === "progress");
  const activeCap = mappedCaptions.find((s) => t >= s.eStart && t < s.eEnd) ?? null;
  const punchActive = mappedGraphics.some((g) => g.type === "punch-in" && t >= g.eStart && t < g.eEnd);

  const doSeekEdit = (et: number) => {
    const c = clamp(et, 0, Math.max(0, dur - 0.02));
    if (src && videoRef.current) {
      const s = editToSource(spansRef.current, c);
      if (s != null) videoRef.current.currentTime = s;
    } else {
      clockRef.current.t = c;
    }
    setT(c);
  };

  useImperativeHandle(
    ref,
    () => ({
      toggle: () => {
        if (src && videoRef.current) {
          if (videoRef.current.paused) void videoRef.current.play().catch(() => {});
          else videoRef.current.pause();
        } else {
          setPlaying((p) => {
            if (!p) clockRef.current.last = 0;
            return !p;
          });
        }
      },
      seekEdit: doSeekEdit,
      step: (delta: number) => {
        const base = src && videoRef.current
          ? sourceToEdit(spansRef.current, videoRef.current.currentTime) ?? t
          : t;
        doSeekEdit(base + delta);
      },
      isPlaying: () => (src && videoRef.current ? !videoRef.current.paused : playing),
      requestSeek: (nt: number) => doSeekEdit(nt),
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [src, dur, t, playing]
  );

  useEffect(() => {
    const loop = (now: number) => {
      rafRef.current = requestAnimationFrame(loop);
      const sp = spansRef.current;
      if (src && videoRef.current) {
        const v = videoRef.current;
        if (!v.paused && !v.seeking) {
          const srcT = v.currentTime;
          const span = spanAtSource(sp, srcT);
          if (!span) {
            // inside a removed gap — jump to the next kept start
            const next = nextKeptStart(sp, srcT);
            if (next != null) v.currentTime = next + 0.001;
            else v.pause();
            return;
          }
          const ed = sourceToEdit(sp, srcT);
          if (ed != null) setT(ed);
          const want = span.speed || 1;
          if (Math.abs(v.playbackRate - want) > 0.01) v.playbackRate = want;
        } else {
          const ed = sourceToEdit(sp, v.currentTime);
          if (ed != null) setT((prev) => (Math.abs(ed - prev) > 0.05 ? ed : prev));
        }
      } else if (playing) {
        const last = clockRef.current.last || now;
        const dt = (now - last) / 1000;
        clockRef.current.last = now;
        let nt = clockRef.current.t + dt;
        if (nt >= dur) {
          nt = Math.max(0, dur);
          setPlaying(false);
        }
        clockRef.current.t = nt;
        setT(nt);
      } else {
        clockRef.current.last = 0;
      }
      if (now - lastCb.current > 150) {
        lastCb.current = now;
        onTime?.(t);
      }
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src, playing, dur]);

  const posCls =
    captionPosition === "top"
      ? "top-8"
      : captionPosition === "middle"
        ? "top-1/2 -translate-y-1/2"
        : "bottom-8";

  return (
    <div className="relative aspect-video w-full overflow-hidden rounded-xl bg-black select-none">
      {src ? (
        <video
          ref={videoRef}
          src={src}
          className={`h-full w-full object-contain ${punchActive ? "k-punch-video" : ""}`}
          playsInline
          preload="auto"
        />
      ) : (
        <div
          className="flex h-full w-full items-center justify-center"
          style={{
            background:
              "radial-gradient(ellipse 70% 60% at 50% 40%, rgba(225,29,72,0.18), transparent 65%), radial-gradient(ellipse 50% 40% at 70% 80%, rgba(99,102,241,0.15), transparent 60%), #0a0a0b",
          }}
        >
          <div className="text-center">
            <p className="font-display text-2xl font-bold text-white/80">Demo preview</p>
            <p className="mt-1 text-sm text-white/40">No footage loaded — overlays still play in sync</p>
          </div>
        </div>
      )}

      {/* play/pause click layer (below overlays so graphics stay draggable) */}
      <button
        aria-label="toggle play"
        onClick={() => {
          if (src && videoRef.current) {
            if (videoRef.current.paused) void videoRef.current.play().catch(() => {});
            else videoRef.current.pause();
          } else setPlaying((p) => !p);
        }}
        className="absolute inset-0 z-0 cursor-pointer bg-transparent"
      />

      {/* canvas overlay layer */}
      <div data-canvas-layer className="pointer-events-none absolute inset-0 z-10">
        {showProgress && (
          <div className="absolute inset-x-0 top-0 h-1.5 bg-white/10">
            <div
              className="h-full"
              style={{ width: `${dur ? (t / dur) * 100 : 0}%`, background: "var(--brand-gradient)" }}
            />
          </div>
        )}
        {activeGraphics.map((g) => (
          <GraphicOverlay key={`${g.id}-${Math.floor(g.eStart * 10)}`} g={g} brand={brandColor} onMove={onGraphicMove} onEditStart={onEditStart} />
        ))}
        {activeCap && (
          <div className={`absolute inset-x-0 flex justify-center ${posCls}`}>
            <p className="max-w-[90%] rounded-lg bg-black/70 px-4 py-2 text-center text-xl font-semibold leading-snug text-white/90 backdrop-blur-sm">
              {activeCap.words.map((w, i) => {
                const active = t >= w.start && t < w.end;
                return (
                  <span key={i} className={`karaoke-word ${active ? "active" : ""} ${w.emphasis && !active ? "text-[var(--accent)]" : ""}`}>
                    {w.word}{" "}
                  </span>
                );
              })}
            </p>
          </div>
        )}
      </div>
    </div>
  );
});
