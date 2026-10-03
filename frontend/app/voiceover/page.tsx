"use client";
import { useEffect, useState } from "react";
import { Navbar } from "@/components/Navbar";
import { AuthGuard } from "@/components/chrome";
import { Button, Card, Select, Label, Spinner } from "@/components/ui";
import { api, apiBase, ApiError } from "@/lib/api";

const VOICES = ["Aria — warm female", "Marcus — deep male", "Nova — energetic female", "Leo — calm male"];

export default function VoiceoverPage() {
  const [script, setScript] = useState("");
  const [voice, setVoice] = useState(VOICES[0]);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [supported, setSupported] = useState(true);

  useEffect(() => {
    api<{ voices?: string[] }>("/api/v1/voiceover/voices")
      .then((v) => {
        if (v?.voices?.length) {
          // use server voices if provided
        }
      })
      .catch(() => setSupported(false));
  }, []);

  const generate = async () => {
    if (!script.trim()) return;
    setBusy(true);
    setMsg(null);
    try {
      const res = await api<{ audio_url?: string }>("/api/v1/voiceover/generate", {
        method: "POST",
        body: JSON.stringify({ script, voice }),
      });
      const url = res.audio_url ?? null;
      setAudioUrl(url ? (url.startsWith("http") ? url : `${apiBase}${url}`) : null);
      setMsg("Voiceover generated. Preview it below, then attach it to a project from the timeline's Audio track.");
    } catch (e) {
      setMsg(e instanceof ApiError ? `Generation failed: ${e.message}` : "Generation failed.");
    } finally {
      setBusy(false);
    }
  };

  const wordCount = script.trim().split(/\s+/).filter(Boolean).length;

  return (
    <AuthGuard>
      <div className="min-h-screen bg-black">
        <Navbar />
        <main className="mx-auto max-w-4xl px-4 py-10 sm:px-6">
          <h1 className="font-display text-3xl font-bold">Voiceover studio</h1>
          <p className="mt-1 text-[var(--muted-fg)]">Write or paste a script, pick a voice, generate an AI voiceover track for faceless videos.</p>

          {!supported ? (
            <Card className="mt-8 p-8 text-center">
              <p className="font-display text-lg font-semibold">Voiceover isn't enabled on this server yet</p>
              <p className="mx-auto mt-2 max-w-md text-sm text-[var(--muted-fg)]">
                The TTS endpoint is built by Worker E. You can still draft your script below — it'll be ready to paste the moment the API lands.
              </p>
            </Card>
          ) : null}

          <Card className="mt-8 p-6">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <Label>Voice</Label>
                <Select value={voice} onChange={(e) => setVoice(e.target.value)} className="w-full">
                  {VOICES.map((v) => <option key={v}>{v}</option>)}
                </Select>
              </div>
              <div className="flex items-end text-sm text-[var(--muted-fg)]">
                {wordCount} words ≈ {Math.ceil(wordCount / 2.5)}s of speech
              </div>
            </div>
            <div className="mt-4">
              <Label>Script</Label>
              <textarea
                value={script}
                onChange={(e) => setScript(e.target.value)}
                rows={8}
                placeholder="Paste your script here…"
                className="w-full rounded-[10px] border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--fg)] placeholder:text-[var(--faint-fg)] focus:border-[var(--accent)] focus:outline-none"
              />
            </div>
            <div className="mt-4 flex items-center gap-3">
              <Button onClick={generate} disabled={busy || !script.trim() || !supported}>
                {busy ? "Generating…" : "Generate voiceover"}
              </Button>
              {busy && <Spinner />}
            </div>
            {msg && <p className="mt-3 text-sm text-[var(--accent)]">{msg}</p>}
            {audioUrl && (
              <div className="mt-5 rounded-[var(--radius-sm)] border border-[var(--border)] bg-[var(--surface)] p-4">
                <p className="mb-2 text-sm font-semibold">Preview</p>
                <audio controls src={audioUrl} className="w-full" />
                <a href={audioUrl} download="voiceover.mp3">
                  <Button variant="outline" size="sm" className="mt-3">Download MP3</Button>
                </a>
              </div>
            )}
          </Card>
        </main>
      </div>
    </AuthGuard>
  );
}
