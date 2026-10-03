// Cut-aware time mapping for the CutPilot timeline editor.
// Kept spans are stored in SOURCE media time; the timeline shows EDITED time.
import type { KeptSpan } from "@/lib/types";

export interface EditedSpan extends KeptSpan {
  editStart: number; // edited-time start
  editEnd: number;   // edited-time end
  editLen: number;
}

export function toEditedSpans(spans: KeptSpan[]): EditedSpan[] {
  let acc = 0;
  return [...spans]
    .sort((a, b) => 0) // keep playback order as given
    .map((s) => {
      const speed = s.speed && s.speed > 0 ? s.speed : 1;
      const editLen = (s.end - s.start) / speed;
      const e: EditedSpan = { ...s, speed, editStart: acc, editEnd: acc + editLen, editLen };
      acc += editLen;
      return e;
    });
}

export function editedDuration(spans: EditedSpan[]): number {
  return spans.length ? spans[spans.length - 1].editEnd : 0;
}

/** edited time -> source time (null if out of range) */
export function editToSource(spans: EditedSpan[], t: number): number | null {
  for (const s of spans) {
    if (t >= s.editStart && t < s.editEnd) {
      return s.start + (t - s.editStart) * (s.speed || 1);
    }
  }
  if (spans.length && t >= spans[spans.length - 1].editEnd) {
    const last = spans[spans.length - 1];
    return last.end;
  }
  return null;
}

/** source time -> edited time (null if inside a removed gap) */
export function sourceToEdit(spans: EditedSpan[], src: number): number | null {
  for (const s of spans) {
    if (src >= s.start && src < s.end) {
      return s.editStart + (src - s.start) / (s.speed || 1);
    }
  }
  return null;
}

/** Given source time, find the span containing it (or the next kept span after a gap). */
export function spanAtSource(spans: EditedSpan[], src: number): EditedSpan | null {
  for (const s of spans) {
    if (src >= s.start && src < s.end) return s;
  }
  return null;
}

export function nextKeptStart(spans: EditedSpan[], src: number): number | null {
  const sorted = [...spans].sort((a, b) => a.start - b.start);
  for (const s of sorted) {
    if (s.start > src + 0.001) return s.start;
  }
  return null;
}

export function spanAtEdit(spans: EditedSpan[], t: number): EditedSpan | null {
  for (const s of spans) {
    if (t >= s.editStart && t < s.editEnd) return s;
  }
  return null;
}

export function uid(prefix = "c"): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 9)}${Date.now().toString(36).slice(-4)}`;
}

export function clamp(n: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, n));
}
