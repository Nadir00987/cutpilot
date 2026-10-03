// Synthetic demo edit plan — lets the timeline editor be explored
// instantly without a backend or uploaded footage.
import type { EditPlan, KeptSpan, Graphic, CaptionSegment } from "@/lib/types";
import { uid } from "./timeMath";

const WORDS = "cutpilot ai turns raw footage into a polished edit automatically".split(" ");

function buildCaptions(): CaptionSegment[] {
  const segs: CaptionSegment[] = [];
  let t = 0.5;
  let wi = 0;
  for (let s = 0; s < 8; s++) {
    const words = [];
    const n = 5;
    for (let i = 0; i < n; i++) {
      const w = WORDS[wi % WORDS.length];
      words.push({ word: w, start: t, end: t + 0.42, emphasis: wi % 4 === 0 });
      t += 0.44;
      wi++;
    }
    segs.push({ id: uid("cap"), start: words[0].start, end: words[words.length - 1].end, words });
    t += 1.6; // pause between lines
  }
  return segs;
}

export function demoPlan(): EditPlan {
  const cuts: KeptSpan[] = [
    { id: uid("k"), start: 0, end: 8.2, label: "Intro hook" },
    { id: uid("k"), start: 10.5, end: 17.8, label: "Main point 1" },
    { id: uid("k"), start: 19.2, end: 26.4, label: "Main point 2", speed: 1.1 },
    { id: uid("k"), start: 30.0, end: 38.6, label: "Demo" },
    { id: uid("k"), start: 41.3, end: 47.9, label: "Outro CTA" },
  ];
  const graphics: Graphic[] = [
    { id: uid("g"), type: "kinetic", start: 0.4, end: 3.4, text: "STOP EDITING MANUALLY", style: "scale-pop", reason: "Hook emphasis" },
    { id: uid("g"), type: "lower-third", start: 1.2, end: 6.5, text: "Alex Creator — Video Coach", style: "slide-up" },
    { id: uid("g"), type: "punch-in", start: 11.0, end: 12.2, style: "punch", reason: "Emphasis word" },
    { id: uid("g"), type: "callout", start: 12.5, end: 16.0, text: "Key insight #1", style: "bounce", x: 68, y: 22 },
    { id: uid("g"), type: "stat", start: 20.0, end: 24.0, text: "10x faster edits", style: "scale-pop", x: 50, y: 30 },
    { id: uid("g"), type: "emoji", start: 24.5, end: 26.0, text: "🔥", style: "bounce", x: 78, y: 60 },
    { id: uid("g"), type: "quote", start: 31.0, end: 36.5, text: "“It edits like I would — only faster.”", style: "fade-blur" },
    { id: uid("g"), type: "subscribe", start: 42.0, end: 47.5, text: "Subscribe for more", style: "slide-up", x: 50, y: 78 },
    { id: uid("g"), type: "progress", start: 0, end: 47.9, style: "bar" },
  ];
  return {
    version: 1,
    cuts,
    graphics,
    captions: { style: "hormozi", position: "bottom", segments: buildCaptions() },
    broll: [
      { id: uid("b"), start: 12.5, end: 16.0, keyword: "editing timeline", label: "B-roll: timeline close-up" },
      { id: uid("b"), start: 31.0, end: 36.5, keyword: "creator studio", label: "B-roll: studio" },
    ],
    music: { track: "Energetic — Upbeat Pop 03", ducking: true },
    reasons: {
      "gap 8.2–10.5": "Removed: filler + long pause (confidence 0.97)",
      "gap 26.4–30.0": "Removed: repeated take (confidence 0.91)",
    },
  };
}
