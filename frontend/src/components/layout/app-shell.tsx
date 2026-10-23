"use client";

import { Gauge, Goal, History, LogOut, Menu, Settings, Sparkles, UserRound, Users, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";

import { CustomerPicker } from "@/components/customers/customer-picker";
import { ErrorState, LoadingState, cn } from "@/components/shared/ui";
import { SessionProvider, useSession } from "@/hooks/use-session";
import { signOut } from "@/lib/auth";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: Gauge },
  { href: "/insights", label: "Money coach", icon: Sparkles },
  { href: "/goals", label: "Goals", icon: Goal },
  { href: "/recommendations", label: "History", icon: History },
  { href: "/customers", label: "Profile", icon: UserRound, advisorLabel: "Customers", advisorIcon: Users },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <SessionProvider>
      <Shell>{children}</Shell>
    </SessionProvider>
  );
}

function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { me, error, loading, refreshMe } = useSession();
  const [open, setOpen] = useState(false);
  const isAdvisor = me?.role === "advisor";

  const nav = (
    <nav aria-label="Main" className="flex flex-col gap-1">
      {NAV.map((item) => {
        const Icon = isAdvisor && item.advisorIcon ? item.advisorIcon : item.icon;
        const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={() => setOpen(false)}
            aria-current={active ? "page" : undefined}
            className={cn("flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium", active ? "bg-white/10 text-white" : "text-slate-300 hover:bg-white/5 hover:text-white")}
          >
            <Icon className="size-4" aria-hidden />
            {isAdvisor && item.advisorLabel ? item.advisorLabel : item.label}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <div className="min-h-screen lg:flex">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2">
        Skip to content
      </a>
      <aside className={cn("fixed inset-y-0 left-0 z-40 w-64 flex-col bg-navy p-4 lg:static lg:flex", open ? "flex" : "hidden")}>
        <div className="mb-8 flex items-center justify-between px-2">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-teal-300">EXL</p>
            <p className="text-base font-semibold text-white">Financial Wellness Coach</p>
          </div>
          <button type="button" className="text-slate-300 lg:hidden" onClick={() => setOpen(false)} aria-label="Close menu">
            <X className="size-5" />
          </button>
        </div>
        {nav}
        <div className="mt-auto rounded-lg bg-white/5 p-3 text-xs text-slate-300">
          All figures are computed from <strong className="text-white">synthetic</strong> data. This is a demo, not regulated financial advice.
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="bg-navy-2 px-4 py-1.5 text-center text-xs font-medium text-white" role="note">
          Simulated data environment — no real customer or bank data is used.
        </div>
        <header className="flex flex-wrap items-center gap-3 border-b border-line bg-surface px-4 py-3 lg:px-8">
          <button type="button" className="rounded-md p-1 text-ink-2 lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu">
            <Menu className="size-5" />
          </button>
          <div className="min-w-0 flex-1">{me && (isAdvisor ? <CustomerPicker /> : <p className="truncate text-sm text-ink-2">Welcome back, <span className="font-medium text-ink">{me.display_name}</span></p>)}</div>
          {me && (
            <div className="flex items-center gap-3">
              <span className="hidden text-right text-xs text-ink-3 sm:block">
                <span className="block font-medium text-ink">{me.display_name}</span>
                {isAdvisor ? "Advisor (read-only)" : "Customer"}
              </span>
              <button type="button" onClick={() => void signOut()} className="inline-flex items-center gap-1 rounded-lg border border-line px-3 py-1.5 text-sm text-ink-2 hover:bg-slate-50">
                <LogOut className="size-4" aria-hidden /> Sign out
              </button>
            </div>
          )}
        </header>
        <main id="main" className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 lg:px-8">
          {loading && <LoadingState label="Loading your profile…" />}
          {error && <ErrorState error={error} onRetry={refreshMe} />}
          {me && children}
        </main>
      </div>
    </div>
  );
}
