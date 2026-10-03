// CutPilot AI — shared TypeScript types (frontend mirror of the backend contract)

export interface User {
  id: string;
  email: string;
  name?: string;
  role: "user" | "admin";
  credits?: number;
}

export interface Project {
  id: string;
  name: string;
  status: "uploading" | "analyzing" | "ready" | "rendering" | "done" | "error";
  duration?: number;
  thumbnail_url?: string | null;
  created_at?: string;
  updated_at?: string;
  width?: number;
  height?: number;
  fps?: number;
}

/** A kept segment of the source video. All times in seconds (source media time). */
export interface KeptSpan {
  id: string;
  start: number;
  end: number;
  speed?: number; // 0.5–2
  label?: string;
}

export interface CaptionWord {
  word: string;
  start: number; // source time
  end: number;   // source time
  emphasis?: boolean;
}

export interface CaptionSegment {
  id: string;
  start: number; // source time
  end: number;   // source time
  words: CaptionWord[];
}

export type GraphicType =
  | "kinetic"
  | "lower-third"
  | "callout"
  | "stat"
  | "emoji"
  | "quote"
  | "progress"
  | "punch-in"
  | "subscribe";

export interface Graphic {
  id: string;
  type: GraphicType;
  start: number; // source time
  end: number;   // source time
  text?: string;
  x?: number; // 0–100 (percent)
  y?: number; // 0–100 (percent)
  style?: string; // animation style: scale-pop | slide-up | typewriter | bounce | fade-blur
  reason?: string;
}

export interface BrollClip {
  id: string;
  start: number;
  end: number;
  keyword?: string;
  url?: string;
  label?: string;
}

export interface EditPlan {
  version: number;
  cuts?: KeptSpan[];           // kept spans ("smart cuts" result)
  removed?: { start: number; end: number; reason?: string }[]; // alternative representation
  graphics?: Graphic[];
  captions?: {
    style?: string;
    position?: "top" | "middle" | "bottom";
    segments?: CaptionSegment[];
  };
  broll?: BrollClip[];
  music?: { track?: string; ducking?: boolean };
  brand?: { primary_color?: string; logo_url?: string };
  reasons?: Record<string, string>;
  [k: string]: unknown;
}

export interface Analysis {
  transcript?: string;
  words?: CaptionWord[];
  fillers?: { start: number; end: number; text?: string; action?: string }[];
  silences?: { start: number; end: number }[];
  scenes?: { start: number; end: number; description?: string }[];
  speakers?: { start: number; end: number; speaker?: string }[];
  energy?: { start: number; end: number; score?: number }[];
  hook?: { start: number; end: number; text?: string };
  keywords?: Array<string | { phrase: string; score?: number; start?: number; end?: number }>;
  audio_qc?: { noise_level?: number; clipping?: boolean; notes?: string };
  summary?: string;
  suggested_title?: string;
  thumbnail_options?: string[];
  language?: string;
  duration?: number;
  [k: string]: unknown;
}

export interface RenderJob {
  id: string;
  project_id?: string;
  preset?: string;
  status: "queued" | "rendering" | "done" | "failed";
  progress?: number;
  eta_seconds?: number;
  download_url?: string;
  created_at?: string;
}

export interface ShortClip {
  id: string;
  start?: number;
  end?: number;
  duration?: number;
  title?: string;
  download_url?: string;
  thumbnail_url?: string;
  score?: number;
}

export interface Template {
  id: string;
  name: string;
  category?: string;
  description?: string;
  preview_url?: string;
  accent?: string;
}

export interface Plan {
  id: string;
  name: string;
  price?: number;
  credits?: number;
  interval?: string;
}

export interface ProgressMsg {
  stage: string;
  pct: number;
  message?: string;
}
