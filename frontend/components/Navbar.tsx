"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { useAuth } from "@/lib/auth";
import { Button } from "./ui";
import { cn } from "@/lib/utils";

export function Logo() {
  return (
    <Link href="/" className="flex cursor-pointer items-center gap-2.5">
      <span className="flex h-9 w-9 items-center justify-center rounded-xl" style={{ background: "var(--brand-gradient)" }}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="white">
          <path d="M8 5v14l11-7z" />
        </svg>
      </span>
      <span className="font-display text-xl font-700 font-bold tracking-tight">
        CutPilot<span style={{ color: "var(--accent)" }}> AI</span>
      </span>
    </Link>
  );
}

const NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/templates", label: "Templates" },
  { href: "/brand-kit", label: "Brand Kit" },
  { href: "/billing", label: "Billing" },
];

export function Navbar() {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  if (pathname.startsWith("/project/")) return null; // editor has its own chrome

  return (
    <motion.header
      initial={{ y: -24, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
      className="sticky top-0 z-50 border-b border-[var(--border)] bg-[rgba(0,0,0,0.82)] backdrop-blur-xl"
    >
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6">
        <Logo />
        {user ? (
          <nav className="flex items-center gap-1">
            {NAV.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                className={cn(
                  "cursor-pointer rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  pathname === n.href || pathname.startsWith(n.href + "/")
                    ? "text-white bg-[var(--muted-bg)]"
                    : "text-[var(--muted-fg)] hover:text-white"
                )}
              >
                {n.label}
              </Link>
            ))}
            <span className="ml-2 hidden rounded-full bg-[var(--accent-soft)] px-3 py-1 text-xs font-semibold text-[var(--accent)] sm:inline">
              {user.credits ?? "—"} credits
            </span>
            <Button variant="ghost" size="sm" onClick={logout} className="ml-1">
              Log out
            </Button>
          </nav>
        ) : (
          <div className="flex items-center gap-2">
            <Link href="/auth/login">
              <Button variant="ghost" size="sm">Log in</Button>
            </Link>
            <Link href="/auth/signup">
              <Button size="sm">Start free</Button>
            </Link>
          </div>
        )}
      </div>
    </motion.header>
  );
}

export function Footer() {
  return (
    <footer className="border-t border-[var(--border)] bg-black">
      <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 px-6 py-10 sm:flex-row">
        <Logo />
        <p className="text-sm text-[var(--muted-fg)]">
          CutPilot AI — the auto video-editing studio. Edits like a human. Ships like a machine.
        </p>
        <div className="flex gap-5 text-sm text-[var(--muted-fg)]">
          <Link href="/templates" className="cursor-pointer hover:text-white">Templates</Link>
          <Link href="/billing" className="cursor-pointer hover:text-white">Pricing</Link>
          <Link href="/auth/login" className="cursor-pointer hover:text-white">Log in</Link>
        </div>
      </div>
    </footer>
  );
}
