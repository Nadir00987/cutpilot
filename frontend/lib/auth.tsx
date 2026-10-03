"use client";
import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, setTokens, clearTokens, getAccessToken } from "./api";
import type { User } from "./types";

interface AuthCtx {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    if (!getAccessToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await api<User>("/api/v1/auth/me");
      setUser(me);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const login = useCallback(async (email: string, password: string) => {
    // Backend uses the OAuth2 password flow: form-encoded username + password
    const form = new URLSearchParams();
    form.set("username", email);
    form.set("password", password);
    const data = await api<{ access_token: string; refresh_token: string; user: User }>(
      "/api/v1/auth/login",
      {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: form.toString(),
      }
    );
    setTokens(data.access_token, data.refresh_token);
    // Newer backends include the user in the login response; older ones don't —
    // fall back to /me so the auth guard never sees a null user after login.
    if (data.user) {
      setUser(data.user);
    } else {
      try {
        const me = await api<User>("/api/v1/auth/me");
        setUser(me);
      } catch {
        setUser(null);
      }
    }
  }, []);

  const signup = useCallback(async (name: string, email: string, password: string) => {
    const data = await api<{ access_token: string; refresh_token: string; user: User }>(
      "/api/v1/auth/signup",
      { method: "POST", body: JSON.stringify({ name, email, password }) }
    );
    setTokens(data.access_token, data.refresh_token);
    if (data.user) {
      setUser(data.user);
    } else {
      try {
        const me = await api<User>("/api/v1/auth/me");
        setUser(me);
      } catch {
        setUser(null);
      }
    }
  }, []);

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
    if (typeof window !== "undefined") window.location.href = "/auth/login";
  }, []);

  return (
    <Ctx.Provider value={{ user, loading, login, signup, logout, refreshUser }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAuth(): AuthCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
