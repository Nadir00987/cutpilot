"use client";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { ResetForm } from "@/components/auth-forms";

function Inner() {
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  if (!token) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-black px-4">
        <p className="text-[var(--muted-fg)]">
          This reset link is missing its token. Request a new one from the{" "}
          <a href="/auth/forgot-password" className="text-[var(--accent)]">forgot-password page</a>.
        </p>
      </div>
    );
  }
  return <ResetForm token={token} />;
}

export default function ResetPage() {
  return (
    <Suspense fallback={null}>
      <Inner />
    </Suspense>
  );
}
