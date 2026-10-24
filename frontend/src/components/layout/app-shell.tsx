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

function Wordmark() {
  return (
    <Link href="/dashboard" className="flex items-center gap-2.5 rounded-md px-1 py-1">
      <span aria-hidden className="grid size-8 place-items-center rounded-md bg-gradient-to-br from-primary to-primary-warm text-sm font-bold text-white">
        E
      </span>
      <span className="leading-tight">
        <span className="block text-[11px] font-semibold uppercase tracking-wider text-white/60">EXL</span>
        <span className="block text-sm font-bold text-white">Financial Wellness Coach</span>
      </span>
    </Link>
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
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-1.5 text-[13px] font-bold leading-6 transition-colors duration-150 ease-standard",
              active ? "bg-primary-ink text-white" : "text-white/70 hover:bg-primary-ink hover:text-white",
            )}
          >
            <Icon className="size-4" aria-hidden />
            {isAdvisor && item.advisorLabel ? item.advisorLabel : item.label}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <div className="min-h-screen bg-background">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-surface-elevated focus:px-3 focus:py-2">
        Skip to content
      </a>

      {/* Top bar: dark glass across the full width */}
      <header className="shell-glass fixed inset-x-0 top-0 z-40 flex h-16 items-center gap-3 border-b border-white/10 px-4">
        <button
          type="button"
          className="grid size-10 place-items-center rounded-md text-white/70 hover:bg-white/10 hover:text-white lg:hidden"
          onClick={() => setOpen(true)}
          aria-label="Open menu"
        >
          <Menu className="size-5" />
        </button>
        <div className="hidden w-[224px] shrink-0 lg:block">
          <Wordmark />
        </div>
        <div className="min-w-0 flex-1">
          {me &&
            (isAdvisor ? (
              <CustomerPicker />
            ) : (
              <p className="truncate text-sm text-white/70">
                Welcome back, <span className="font-semibold text-white">{me.display_name}</span>
              </p>
            ))}
        </div>
        <span className="hidden rounded-full bg-status-mock-bg px-2.5 py-1 text-xs font-semibold text-status-mock-fg md:inline">Simulated data</span>
        {me && (
          <div className="flex items-center gap-2">
            <span className="hidden text-right text-xs leading-tight text-white/60 sm:block">
              <span className="block font-semibold text-white">{me.display_name}</span>
              {isAdvisor ? "Advisor · read-only" : "Customer"}
            </span>
            <button
              type="button"
              onClick={() => void signOut()}
              className="grid size-10 place-items-center rounded-md text-white/70 transition-colors duration-150 hover:bg-primary-ink hover:text-white"
              aria-label="Sign out"
              title="Sign out"
            >
              <LogOut className="size-4" aria-hidden />
            </button>
          </div>
        )}
      </header>

      {/* Sidebar: dark glass, 256px; slides in on small screens */}
      {open && <div className="fixed inset-0 z-40 bg-black/30 lg:hidden" onClick={() => setOpen(false)} aria-hidden />}
      <aside
        className={cn(
          "shell-glass fixed bottom-0 left-0 z-50 flex w-64 flex-col border-r border-white/10 p-4 transition-transform duration-300 ease-standard lg:top-16 lg:z-30 lg:translate-x-0",
          open ? "top-0 translate-x-0" : "top-0 -translate-x-full",
        )}
      >
        <div className="mb-6 flex items-center justify-between lg:hidden">
          <Wordmark />
          <button type="button" className="grid size-10 place-items-center rounded-md text-white/70 hover:bg-white/10" onClick={() => setOpen(false)} aria-label="Close menu">
            <X className="size-5" />
          </button>
        </div>
        {nav}
        <div className="mt-auto rounded-md border border-white/10 bg-white/5 p-3 text-xs leading-5 text-white/70">
          All figures are computed from <strong className="text-white">synthetic</strong> data. This is a demo, not regulated financial advice.
        </div>
      </aside>

      <main id="main" className="pt-16 lg:pl-64">
        <div className="mx-auto w-full max-w-[1400px] px-4 py-8 sm:px-8">
          {loading && <LoadingState label="Loading your profile…" />}
          {error && <ErrorState error={error} onRetry={refreshMe} />}
          {me && children}
        </div>
      </main>
    </div>
  );
}
