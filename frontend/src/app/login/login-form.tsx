"use client";

import { Loader2 } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { signIn } from "@/lib/auth";
import { validateLogin, type FieldErrors } from "@/lib/validation";

function safeNext(value: string | null): string {
  // Only allow internal paths to avoid open redirects.
  return value && value.startsWith("/") && !value.startsWith("//") ? value : "/dashboard";
}

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const found = validateLogin(email, password);
    setErrors(found);
    setFormError(null);
    if (Object.keys(found).length) return;
    setBusy(true);
    const result = await signIn(email, password);
    setBusy(false);
    if (result.ok) {
      router.replace(safeNext(params.get("next")));
      router.refresh();
    } else {
      setFormError(result.message);
      setPassword("");
    }
  }

  const input = (invalid: boolean) =>
    `mt-1 block h-10 w-full rounded-sm border bg-surface-elevated px-3 text-sm text-ink transition-colors duration-150 focus:border-primary ${invalid ? "border-danger" : "border-outline-strong"}`;

  return (
    <form onSubmit={submit} noValidate className="space-y-4" aria-label="Sign in">
      <label className="block text-sm">
        <span className="font-medium text-ink">Email</span>
        <input
          type="email"
          autoComplete="username"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          aria-invalid={Boolean(errors.email)}
          aria-describedby={errors.email ? "email-error" : undefined}
          className={input(Boolean(errors.email))}
        />
        {errors.email && <span id="email-error" className="mt-1 block text-xs text-danger-ink">{errors.email}</span>}
      </label>
      <label className="block text-sm">
        <span className="font-medium text-ink">Password</span>
        <input
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          aria-invalid={Boolean(errors.password)}
          aria-describedby={errors.password ? "password-error" : undefined}
          className={input(Boolean(errors.password))}
        />
        {errors.password && <span id="password-error" className="mt-1 block text-xs text-danger-ink">{errors.password}</span>}
      </label>
      {formError && (
        <p role="alert" className="rounded-sm bg-status-danger-bg/60 px-3 py-2 text-sm text-danger-ink">
          {formError}
        </p>
      )}
      <button type="submit" disabled={busy} className="flex h-10 w-full items-center justify-center gap-2 rounded-sm bg-primary-ink px-4 text-sm font-medium text-white transition-colors duration-150 hover:bg-primary-ink/90 disabled:bg-outline-strong disabled:text-ink-muted">
        {busy && <Loader2 className="size-4 animate-spin" aria-hidden />}
        {busy ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
