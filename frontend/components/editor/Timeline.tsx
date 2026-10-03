"use client";
import { useMemo, useRef, useState } from "react";
import { EditedSpan, clamp } from "./timeMath";
import { fmtTime } from "@/lib/api";

export interface Selection {
  track: string;
  id: string;
}

export interface TLItem {
  id: string;
  eStart: number;
  eEnd: number;
  label?: string;
  color: string;
}

interface Props {
  spans: EditedSpan[];
  tracks: { key: string; label: string; color: string; items: TLItem[]; height: number }[];
  playhead: number;
  pxPerSec: number;
  selected: Selection | null;
  onSelect: (s: Selection | null) => void;
  onSeek: (t: number) => void;
  /** trim a video span edge (source-time); returns clamped value handled by parent */
  onTrimSpan: (id: string, edge: "l" | "r", newSource: number) => void;
  onReorderSpan: (id: string, toIndex: number) => void;
  /** called once when a trim/move gesture starts, so undo captures the pre-gesture state */
  onEditStart?: () => void;
  duration: number;
}

function tickStep(pxPerSec: number): number {
  if (pxPerSec >= 60) return 1;
  if (pxPerSec >= 24) return 5;
  if (pxPerSec >= 8) return 15;
  return 30;
}

export function Timeline({
  spans, tracks, playhead, pxPerSec, selected, onSelect, onSeek, onTrimSpan, onReorderSpan, onEditStart, duration,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<{
    kind: "trim-l" | "trim-r" | "move";
    trackKey: string;
    id: string;
    startX: number;
    origEditStart: number;
    origEditEnd: number;
    spanId: string;
  } | null>(null);
  const width = Math.max(600, duration * pxPerSec + 120);

  const ticks = useMemo(() => {
    const step = tickStep(pxPerSec);
    const arr: number[] = [];
    for (let s = 0; s <= duration + step; s += step) arr.push(s);
    return arr;
  }, [duration, pxPerSec]);

  const seekFromEvent = (e: React.MouseEvent) => {
    const el = (e.currentTarget as HTMLElement).querySelector("[data-tl-body]") as HTMLElement | null;
    const body = el ?? (e.currentTarget as HTMLElement);
    const rect = body.getBoundingClientRect();
    const t = clamp((e.clientX - rect.left) / pxPerSec, 0, duration);
    onSeek(t);
  };

  const startTrim = (e: React.PointerEvent, trackKey: string, span: EditedSpan, edge: "l" | "r") => {
    e.stopPropagation();
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    onEditStart?.();
    setDrag({
      kind: edge === "l" ? "trim-l" : "trim-r",
      trackKey, id: span.id, startX: e.clientX,
      origEditStart: span.editStart, origEditEnd: span.editEnd, spanId: span.id,
    });
  };

  const startMove = (e: React.PointerEvent, trackKey: string, span: EditedSpan) => {
    if (trackKey !== "video") return;
    e.stopPropagation();
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    onEditStart?.();
    setDrag({
      kind: "move", trackKey, id: span.id, startX: e.clientX,
      origEditStart: span.editStart, origEditEnd: span.editEnd, spanId: span.id,
    });
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (!drag) return;
    const dEdit = (e.clientX - drag.startX) / pxPerSec;
    const span = spans.find((s) => s.id === drag.spanId);
    if (!span) return;
    const speed = span.speed || 1;
    if (drag.kind === "trim-l") {
      const newEditStart = clamp(drag.origEditStart + dEdit, 0, drag.origEditEnd - 0.1);
      onTrimSpan(span.id, "l", span.start + (newEditStart - span.editStart) * speed);
    } else if (drag.kind === "trim-r") {
      const newEditEnd = clamp(drag.origEditEnd + dEdit, drag.origEditStart + 0.1, duration);
      onTrimSpan(span.id, "r", span.end + (newEditEnd - span.editEnd) * speed);
    }
  };

  const onPointerUp = (e: React.PointerEvent) => {
    if (!drag) return;
    if (drag.kind === "move") {
      // drop index from pointer x relative to track body
      const body = (e.currentTarget as HTMLElement).querySelector("[data-tl-body]") as HTMLElement | null;
      if (body) {
        const rect = body.getBoundingClientRect();
        const dropT = clamp((e.clientX - rect.left) / pxPerSec, 0, duration);
        let toIndex = spans.length - 1;
        for (let i = 0; i < spans.length; i++) {
          if (dropT < (spans[i].editStart + spans[i].editEnd) / 2) { toIndex = i; break; }
        }
        onReorderSpan(drag.spanId, toIndex);
      }
    }
    setDrag(null);
  };

  const isSel = (track: string, id: string) => selected?.track === track && selected?.id === id;

  return (
    <div
      ref={scrollRef}
      className="slim-scroll overflow-x-auto rounded-[var(--radius)] border border-[var(--border)] bg-[var(--card)]"
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
    >
      <div style={{ width }} className="relative select-none">
        {/* ruler */}
        <div className="sticky top-0 z-20 flex border-b border-[var(--border)] bg-[var(--card)]" style={{ height: 28 }}>
          <div className="w-24 shrink-0 border-r border-[var(--border)]" />
          <div className="relative flex-1" data-tl-body onClick={seekFromEvent}>
            {ticks.map((s) => (
              <div key={s} className="absolute top-0 h-full border-l border-[var(--border)] pl-1 text-[10px] text-[var(--muted-fg)]" style={{ left: s * pxPerSec }}>
                {fmtTime(s)}
              </div>
            ))}
          </div>
        </div>

        {tracks.map((tr) => (
          <div key={tr.key} className="flex border-b border-[var(--border)] last:border-0" style={{ height: tr.height + 8 }}>
            <div className="flex w-24 shrink-0 items-center border-r border-[var(--border)] px-2">
              <span className="text-[10px] font-bold uppercase tracking-wide" style={{ color: tr.color }}>{tr.label}</span>
            </div>
            <div
              className="relative flex-1"
              data-tl-body
              onClick={(e) => {
                if ((e.target as HTMLElement).closest("[data-clip]")) return;
                seekFromEvent(e);
                onSelect(null);
              }}
            >
              {tr.items.map((it) => {
                const left = it.eStart * pxPerSec;
                const w = Math.max(6, (it.eEnd - it.eStart) * pxPerSec);
                const sel = isSel(tr.key, it.id);
                const trimmable = tr.key === "video";
                return (
                  <div
                    key={it.id}
                    data-clip
                    onClick={(e) => { e.stopPropagation(); onSelect({ track: tr.key, id: it.id }); }}
                    onPointerDown={trimmable ? (e) => {
                      const span = spans.find((s) => s.id === it.id);
                      if (span) startMove(e, tr.key, span);
                    } : undefined}
                    className={`tl-clip absolute top-1 overflow-hidden rounded-md ${sel ? "selected" : ""}`}
                    style={{ left, width: w, height: tr.height, background: `${it.color}33`, border: `1px solid ${it.color}` }}
                    title={it.label ?? it.id}
                  >
                    <span className="pointer-events-none block truncate px-1.5 text-[10px] font-semibold leading-[26px] text-white/90">
                      {it.label ?? ""}
                    </span>
                    {trimmable && (
                      <>
                        <span
                          className="tl-trim absolute left-0 top-0 h-full w-2 bg-white/30 hover:bg-white/60"
                          onPointerDown={(e) => {
                            const span = spans.find((s) => s.id === it.id);
                            if (span) startTrim(e, tr.key, span, "l");
                          }}
                        />
                        <span
                          className="tl-trim absolute right-0 top-0 h-full w-2 bg-white/30 hover:bg-white/60"
                          onPointerDown={(e) => {
                            const span = spans.find((s) => s.id === it.id);
                            if (span) startTrim(e, tr.key, span, "r");
                          }}
                        />
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}

        {/* playhead */}
        <div
          className="pointer-events-none absolute top-0 z-10 h-full w-[2px] bg-white"
          style={{ left: 96 + playhead * pxPerSec, boxShadow: "0 0 8px rgba(225,29,72,0.9)" }}
        >
          <div className="absolute -left-[5px] -top-0 h-3 w-3 rotate-45 bg-white" />
        </div>
      </div>
    </div>
  );
}
