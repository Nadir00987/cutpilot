"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import { apiBase, getAccessToken } from "../lib/api";
import type { ProgressMsg } from "../lib/types";

/**
 * Live job progress over WS /api/v1/ws/projects/{id}?token=JWT
 * Messages: { stage, pct, message }
 */
export function useProgress(projectId: string | null, enabled = true) {
  const [progress, setProgress] = useState<ProgressMsg | null>(null);
  const [connected, setConnected] = useState(false);
  const [history, setHistory] = useState<ProgressMsg[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const attempts = useRef(0);

  const connect = useCallback(() => {
    if (!projectId || !enabled) return;
    const token = getAccessToken();
    if (!token) return;
    const wsBase = apiBase.replace(/^http/, "ws");
    let ws: WebSocket;
    try {
      ws = new WebSocket(`${wsBase}/api/v1/ws/projects/${projectId}?token=${token}`);
    } catch {
      return;
    }
    wsRef.current = ws;
    ws.onopen = () => {
      setConnected(true);
      attempts.current = 0;
    };
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data) as ProgressMsg;
        setProgress(msg);
        setHistory((h) => [...h.slice(-99), msg]);
      } catch {
        /* ignore */
      }
    };
    ws.onclose = () => {
      setConnected(false);
      // reconnect with backoff (max ~5 tries)
      if (attempts.current < 5) {
        attempts.current += 1;
        setTimeout(connect, 1000 * attempts.current * 2);
      }
    };
    ws.onerror = () => ws.close();
  }, [projectId, enabled]);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);

  return { progress, connected, history };
}
