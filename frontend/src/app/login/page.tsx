import type { Metadata } from "next";
import { Suspense } from "react";

import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  const supabaseMode = process.env.AUTH_MODE === "supabase";
  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-6 text-center">
          <p className="text-xs font-semibold uppercase tracking-widest text-teal-ink">EXL Live Project</p>
          <h1 className="mt-1 text-2xl font-semibold text-ink">Financial Wellness Coach</h1>
          <p className="mt-1 text-sm text-ink-2">Personalised, explainable money guidance</p>
        </div>
        <div className="rounded-xl border border-line bg-surface p-6 shadow-sm">
          <Suspense fallback={null}>
            <LoginForm />
          </Suspense>
        </div>
        <div className="mt-4 rounded-xl border border-teal/20 bg-teal-soft p-4 text-sm text-ink-2">
          <p className="font-medium text-ink">Demo instructions</p>
          {supabaseMode ? (
            <p className="mt-1">Sign in with a demo account created by your project administrator in Supabase Auth.</p>
          ) : (
            <ul className="mt-1 list-disc space-y-1 pl-5">
              <li>
                Customer view: <code className="text-xs">customer01@demo.exl.test</code> (any number 01–60)
              </li>
              <li>
                Advisor view (read-only, all customers): <code className="text-xs">advisor@demo.exl.test</code>
              </li>
              <li>
                The password is the <code className="text-xs">LOCAL_DEMO_PASSWORD</code> value in <code className="text-xs">backend/.env</code>.
              </li>
            </ul>
          )}
          <p className="mt-2 text-xs text-ink-3">All people, accounts and transactions are synthetic. Nothing here is real bank data or regulated financial advice.</p>
        </div>
      </div>
    </main>
  );
}
