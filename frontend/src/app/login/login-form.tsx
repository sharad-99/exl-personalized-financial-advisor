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

  const input = (invalid: boolean) => `mt-1 block w-full rounded-lg border px-3 py-2 text-sm ${invalid ? "border-bad" : "border-line"}`;

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
        {errors.email && <span id="email-error" className="mt-1 block text-xs text-bad">{errors.email}</span>}
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
        {errors.password && <span id="password-error" className="mt-1 block text-xs text-bad">{errors.password}</span>}
      </label>
      {formError && (
        <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-bad">
          {formError}
        </p>
      )}
      <button type="submit" disabled={busy} className="flex w-full items-center justify-center gap-2 rounded-lg bg-navy px-4 py-2.5 text-sm font-medium text-white hover:bg-navy-2 disabled:bg-slate-400">
        {busy && <Loader2 className="size-4 animate-spin" aria-hidden />}
        {busy ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
