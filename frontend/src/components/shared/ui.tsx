import { AlertTriangle, CheckCircle2, Clock, Inbox, Info, Loader2, RefreshCw, XCircle } from "lucide-react";
import type { ReactNode } from "react";

import type { ApiError } from "@/lib/api-client";
import type { Confidence } from "@/types/api";

export function cn(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

export function Card({ title, action, children, className }: { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cn("rounded-xl border border-line bg-surface p-5 shadow-[0_1px_2px_rgba(15,27,45,0.04)]", className)}>
      {(title || action) && (
        <div className="mb-4 flex items-start justify-between gap-3">
          {title && <h2 className="text-sm font-semibold text-ink">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-2">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function StatTile({ label, value, hint, tone = "neutral" }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "neutral" | "good" | "bad" }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-3">{label}</p>
      <p className={cn("mt-1 text-2xl font-semibold tabular-nums", tone === "good" && "text-good", tone === "bad" && "text-bad", tone === "neutral" && "text-ink")}>
        {value}
      </p>
      {hint && <p className="mt-1 text-xs text-ink-3">{hint}</p>}
    </div>
  );
}

type Tone = "neutral" | "teal" | "good" | "warn" | "bad" | "navy";
const TONES: Record<Tone, string> = {
  neutral: "bg-slate-100 text-ink-2",
  teal: "bg-teal-soft text-teal-ink",
  good: "bg-green-50 text-good",
  warn: "bg-amber-50 text-warn",
  bad: "bg-red-50 text-bad",
  navy: "bg-navy text-white",
};

export function Badge({ tone = "neutral", children, icon }: { tone?: Tone; children: ReactNode; icon?: ReactNode }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", TONES[tone])}>
      {icon}
      {children}
    </span>
  );
}

export function ConfidenceBadge({ level }: { level: Confidence }) {
  const map = {
    high: { tone: "good" as const, icon: <CheckCircle2 className="size-3" aria-hidden />, label: "High confidence" },
    medium: { tone: "warn" as const, icon: <AlertTriangle className="size-3" aria-hidden />, label: "Medium confidence" },
    low: { tone: "bad" as const, icon: <XCircle className="size-3" aria-hidden />, label: "Low confidence" },
  }[level];
  return (
    <Badge tone={map.tone} icon={map.icon}>
      {map.label}
    </Badge>
  );
}

export function FreshnessBadge({ freshness, days }: { freshness: "fresh" | "aging" | "stale" | "no_data"; days: number | null }) {
  const tone = freshness === "fresh" ? "good" : freshness === "aging" ? "warn" : "bad";
  const label = freshness === "no_data" ? "No transactions" : `Data ${freshness}${days !== null ? ` · ${days}d old` : ""}`;
  return (
    <Badge tone={tone} icon={<Clock className="size-3" aria-hidden />}>
      {label}
    </Badge>
  );
}

export function SyntheticTag() {
  return (
    <Badge tone="navy" icon={<Info className="size-3" aria-hidden />}>
      Synthetic data
    </Badge>
  );
}

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center justify-center gap-2 py-12 text-sm text-ink-3">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      {label}
    </div>
  );
}

export function SkeletonGrid({ count = 4 }: { count?: number }) {
  return (
    <div role="status" aria-label="Loading" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="h-24 animate-pulse rounded-xl border border-line bg-surface" />
      ))}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError | { message: string; requestId?: string }; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-5 text-sm">
      <div className="flex items-start gap-3">
        <XCircle className="mt-0.5 size-5 shrink-0 text-bad" aria-hidden />
        <div className="flex-1">
          <p className="font-medium text-bad">Something went wrong</p>
          <p className="mt-1 text-ink-2">{error.message}</p>
          {"requestId" in error && error.requestId && <p className="mt-1 text-xs text-ink-3">Reference: {error.requestId}</p>}
        </div>
        {onRetry && (
          <button type="button" onClick={onRetry} className="inline-flex items-center gap-1 rounded-md border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-bad hover:bg-red-100">
            <RefreshCw className="size-3" aria-hidden /> Retry
          </button>
        )}
      </div>
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-line bg-surface px-6 py-10 text-center">
      <Inbox className="size-8 text-ink-3" aria-hidden />
      <p className="mt-3 text-sm font-medium text-ink">{title}</p>
      {children && <div className="mt-1 max-w-md text-sm text-ink-2">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warn"; children: ReactNode }) {
  return (
    <div className={cn("flex items-start gap-2 rounded-lg border p-3 text-sm", tone === "warn" ? "border-amber-200 bg-amber-50 text-ink-2" : "border-teal/20 bg-teal-soft text-ink-2")}>
      {tone === "warn" ? <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warn" aria-hidden /> : <Info className="mt-0.5 size-4 shrink-0 text-teal-ink" aria-hidden />}
      <div>{children}</div>
    </div>
  );
}

export function ProgressBar({ value, label }: { value: number; label: string }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)} className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
      <div className="h-full rounded-full bg-teal" style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Button({
  children,
  variant = "primary",
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" }) {
  const styles = {
    primary: "bg-navy text-white hover:bg-navy-2 disabled:bg-slate-300",
    secondary: "border border-line bg-white text-ink hover:bg-slate-50 disabled:text-ink-3",
    ghost: "text-ink-2 hover:bg-slate-100",
  }[variant];
  return (
    <button
      type="button"
      {...props}
      className={cn("inline-flex items-center justify-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed", styles, className)}
    >
      {children}
    </button>
  );
}
