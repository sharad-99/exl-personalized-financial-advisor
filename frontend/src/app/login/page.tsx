import { LineChart, ShieldCheck, Sparkles } from "lucide-react";
import type { Metadata } from "next";
import { Suspense } from "react";

import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Sign in" };

/** Decorative dot-grid "telemetry map". Purely visual; it encodes no data. */
function TelemetryField() {
  const dots = [];
  for (let row = 0; row < 14; row++) {
    for (let col = 0; col < 26; col++) {
      // A soft diagonal band of denser, warmer dots suggests signal moving across the field.
      const band = Math.abs(col - row * 1.6 - 4) < 3;
      const hot = (row * 7 + col * 3) % 23 === 0;
      dots.push(
        <circle
          key={`${row}-${col}`}
          cx={col * 16 + 8}
          cy={row * 16 + 8}
          r={hot ? 3 : band ? 2.2 : 1.4}
          className={hot ? "fill-primary" : band ? "fill-primary-warm" : "fill-outline-strong"}
          opacity={hot ? 0.9 : band ? 0.7 : 0.8}
        />,
      );
    }
  }
  return (
    <svg viewBox="0 0 416 224" className="h-auto w-full max-w-md" aria-hidden>
      {dots}
    </svg>
  );
}

export default function LoginPage() {
  const supabaseMode = process.env.AUTH_MODE === "supabase";
  return (
    <main className="grid min-h-screen bg-background lg:grid-cols-2">
      {/* Brand / visualization half */}
      <section className="order-2 flex flex-col justify-between gap-10 bg-surface-elevated px-8 py-10 sm:px-12 lg:order-1 lg:py-14">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-primary-ink">EXL Live Project</p>
          <p className="mt-4 text-6xl font-semibold leading-none tracking-tight text-ink sm:text-8xl">EXL</p>
          <h1 className="mt-4 text-2xl font-bold text-ink">Financial Wellness Coach</h1>
          <p className="mt-2 max-w-md text-sm text-ink-muted">
            Personalised, explainable money guidance built from income, spending, savings, obligations and goals.
          </p>
        </div>
        <TelemetryField />
        <ul className="grid gap-3 text-sm text-ink sm:grid-cols-3">
          <li className="flex items-start gap-2">
            <LineChart className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden /> Analytics computed from your own data
          </li>
          <li className="flex items-start gap-2">
            <Sparkles className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden /> Every suggestion shows its numbers
          </li>
          <li className="flex items-start gap-2">
            <ShieldCheck className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden /> Your data stays yours alone
          </li>
        </ul>
      </section>

      {/* Orange panel with the white login card */}
      <section className="order-1 flex items-center justify-center bg-primary-strong px-6 py-12 sm:px-8 lg:order-2">
        <div className="w-full max-w-md rounded-md bg-surface-elevated p-8 shadow-dialog">
          <h2 className="text-lg font-bold text-ink">Sign in</h2>
          <p className="mb-6 mt-1 text-sm text-ink-muted">Use your demo account to open the coach.</p>
          <Suspense fallback={null}>
            <LoginForm />
          </Suspense>
          <div className="mt-6 border-t border-outline pt-4 text-sm text-ink-muted">
            <p className="text-xs font-semibold uppercase tracking-wider text-ink-muted">Demo instructions</p>
            {supabaseMode ? (
              <p className="mt-2">Sign in with a demo account created by your project administrator in Supabase Auth.</p>
            ) : (
              <ul className="mt-2 list-disc space-y-1 pl-5">
                <li>
                  Customer view: <code className="font-mono text-xs text-ink">customer01@demo.exl.test</code> (any number 01–60)
                </li>
                <li>
                  Advisor view (read-only): <code className="font-mono text-xs text-ink">advisor@demo.exl.test</code>
                </li>
                <li>
                  Password: <code className="font-mono text-xs text-ink">LOCAL_DEMO_PASSWORD</code> in <code className="font-mono text-xs text-ink">backend/.env</code>
                </li>
              </ul>
            )}
            <p className="mt-3">
              <span className="rounded-full bg-status-mock-bg px-2.5 py-1 text-xs font-semibold text-status-mock-fg">Synthetic data</span>{" "}
              <span className="text-xs">Nothing here is real bank data or regulated financial advice.</span>
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
