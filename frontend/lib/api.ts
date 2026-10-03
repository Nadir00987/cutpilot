// CutPilot AI — fetch wrapper with JWT + refresh-on-401

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

export const apiBase = API_BASE;

const ACCESS_KEY = "cutpilot_access_token";
const REFRESH_KEY = "cutpilot_refresh_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS_KEY);
}
export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_KEY);
}
export function setTokens(access: string, refresh: string) {
  localStorage.setItem(ACCESS_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}
export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

let refreshPromise: Promise<string | null> | null = null;

async function refreshAccess(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;
  const rt = getRefreshToken();
  if (!rt) return null;
  refreshPromise = (async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: rt }),
      });
      if (!res.ok) {
        clearTokens();
        return null;
      }
      const data = await res.json();
      const access = data.access_token ?? data.accessToken;
      const refresh = data.refresh_token ?? data.refreshToken ?? rt;
      if (access) setTokens(access, refresh);
      return access ?? null;
    } catch {
      return null;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

interface ReqOpts extends RequestInit {
  auth?: boolean;
  _retried?: boolean;
}

export async function api<T = unknown>(path: string, opts: ReqOpts = {}): Promise<T> {
  const { auth = true, _retried, ...init } = opts;
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  if (!(init.body instanceof FormData) && init.body !== undefined && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  if (auth) {
    const token = getAccessToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (res.status === 401 && auth && !_retried) {
    const fresh = await refreshAccess();
    if (fresh) return api<T>(path, { ...opts, _retried: true });
    // refresh failed — send user to login
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/auth")) {
      window.location.href = "/auth/login";
    }
    throw new ApiError(401, "Session expired. Please log in again.");
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const msg =
      (data as { detail?: string; message?: string })?.detail ||
      (data as { message?: string })?.message ||
      `Request failed (${res.status})`;
    throw new ApiError(res.status, String(msg));
  }
  return data as T;
}

/** GET with graceful degradation — returns null on 404/network failure. */
export async function apiOptional<T = unknown>(path: string, opts: ReqOpts = {}): Promise<T | null> {
  try {
    return await api<T>(path, opts);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 501)) return null;
    throw e;
  }
}

export function fmtTime(s?: number | null): string {
  if (s == null || Number.isNaN(s)) return "--:--";
  const sec = Math.max(0, Math.floor(s));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const r = sec % 60;
  return h > 0
    ? `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`
    : `${m}:${String(r).padStart(2, "0")}`;
}

export function fmtCredits(n?: number | null): string {
  if (n == null) return "—";
  return n.toLocaleString();
}
