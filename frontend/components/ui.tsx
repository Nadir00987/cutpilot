import React from "react";
import { cn } from "@/lib/utils";

export function Button({
  children,
  variant = "primary",
  size = "md",
  className,
  disabled,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "outline" | "danger" | "soft";
  size?: "sm" | "md" | "lg";
}) {
  return (
    <button
      disabled={disabled}
      className={cn(
        "inline-flex cursor-pointer items-center justify-center gap-2 rounded-[10px] font-semibold transition-all duration-150 focus-visible:outline-2",
        size === "sm" && "px-3 py-1.5 text-sm",
        size === "md" && "px-4 py-2.5 text-sm",
        size === "lg" && "px-6 py-3.5 text-base",
        variant === "primary" &&
          "bg-[var(--accent)] text-white hover:brightness-110 hover:shadow-glow active:scale-[0.98] disabled:opacity-40 disabled:hover:shadow-none disabled:cursor-not-allowed",
        variant === "soft" &&
          "bg-[var(--accent-soft)] text-[var(--accent)] hover:bg-[rgba(225,29,72,0.22)] disabled:opacity-40 disabled:cursor-not-allowed",
        variant === "ghost" && "text-[var(--muted-fg)] hover:text-[var(--fg)] hover:bg-[var(--muted-bg)]",
        variant === "outline" &&
          "border border-[var(--border-strong)] text-[var(--fg)] hover:border-[var(--accent)] hover:text-white",
        variant === "danger" &&
          "bg-[var(--destructive)] text-white hover:brightness-110 disabled:opacity-40 disabled:cursor-not-allowed",
        className
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

export function Card({
  children,
  className,
  ...rest
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-[var(--radius)] border border-[var(--border)] bg-[var(--card)]",
        className
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={cn(
        "w-full rounded-[10px] border border-[var(--border)] bg-[var(--surface)] px-4 py-2.5 text-sm text-[var(--fg)]",
        "placeholder:text-[var(--faint-fg)] focus:border-[var(--accent)] focus:outline-none",
        props.className
      )}
    />
  );
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={cn(
        "rounded-[10px] border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--fg)]",
        "focus:border-[var(--accent)] focus:outline-none",
        props.className
      )}
    />
  );
}

export function Label({ children }: { children: React.ReactNode }) {
  return (
    <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-[var(--muted-fg)]">
      {children}
    </label>
  );
}

export function Spinner({ size = 20 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      className="animate-spin"
      aria-label="loading"
    >
      <circle cx="12" cy="12" r="10" stroke="var(--border-strong)" strokeWidth="4" fill="none" />
      <path d="M22 12a10 10 0 0 0-10-10" stroke="var(--accent)" strokeWidth="4" strokeLinecap="round" fill="none" />
    </svg>
  );
}

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-[var(--radius)] border border-dashed border-[var(--border-strong)] bg-[var(--card)] px-6 py-16 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[var(--accent-soft)]">
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2">
          <path d="M23 7l-7 5 7 5V7z" />
          <rect x="1" y="5" width="15" height="14" rx="2" />
        </svg>
      </div>
      <p className="font-display text-lg font-semibold">{title}</p>
      {hint && <p className="max-w-sm text-sm text-[var(--muted-fg)]">{hint}</p>}
      {action}
    </div>
  );
}

export function ProgressBar({ pct, className }: { pct: number; className?: string }) {
  return (
    <div className={cn("h-2 w-full overflow-hidden rounded-full bg-[var(--muted-bg)]", className)}>
      <div
        className="h-full rounded-full transition-[width] duration-300"
        style={{ width: `${Math.min(100, Math.max(0, pct))}%`, background: "var(--brand-gradient)" }}
      />
    </div>
  );
}
