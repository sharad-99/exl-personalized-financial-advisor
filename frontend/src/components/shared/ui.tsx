import { AlertTriangle, CheckCircle2, Clock, Inbox, Info, Loader2, RefreshCw, XCircle } from "lucide-react";
import type { ReactNode } from "react";

import type { ApiError } from "@/lib/api-client";
import type { Confidence } from "@/types/api";

export function cn(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

/** Quiet analytical card: transparent on the warm canvas, thin outline, subtle shadow, 12px radius. */
export function Card({ title, action, children, className }: { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cn("rounded-lg border border-outline p-6 shadow-subtle", className)}>
      {(title || action) && (
        <div className="mb-4 flex items-start justify-between gap-3">
          {title && <h2 className="text-lg font-bold leading-7 text-ink">{title}</h2>}
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
        <h1 className="text-2xl font-bold leading-8 text-ink">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

/** Small uppercase, tracked label used on cards and tables. */
export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn("text-xs font-semibold uppercase tracking-wider text-ink-muted", className)}>{children}</p>;
}

export function StatTile({ label, value, hint, tone = "neutral" }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "neutral" | "good" | "bad" }) {
  return (
    <div className="relative overflow-hidden rounded-lg border border-outline p-5 shadow-subtle">
      <span aria-hidden className="absolute inset-x-0 top-0 h-0.5 bg-primary/60" />
      <Eyebrow>{label}</Eyebrow>
      <p className={cn("mt-2 text-2xl font-bold tabular-nums", tone === "good" && "text-success-ink", tone === "bad" && "text-danger-ink", tone === "neutral" && "text-ink")}>
        {value}
      </p>
      {hint && <p className="mt-1 text-xs text-ink-muted">{hint}</p>}
    </div>
  );
}

/** Soft, readable status pills mapped onto the spec's status palette. */
type Tone = "neutral" | "primary" | "good" | "warn" | "bad" | "info" | "mock";
const TONES: Record<Tone, string> = {
  neutral: "bg-status-planned-bg text-status-planned-fg",
  primary: "bg-primary/10 text-primary-ink",
  good: "bg-status-production-bg text-status-production-fg",
  warn: "bg-status-mock-bg text-status-mock-fg",
  bad: "bg-status-danger-bg text-danger-ink",
  info: "bg-status-development-bg text-status-development-fg",
  mock: "bg-status-mock-bg text-status-mock-fg",
};

export function Badge({ tone = "neutral", children, icon }: { tone?: Tone; children: ReactNode; icon?: ReactNode }) {
  return (
    <span className={cn("inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold leading-none", TONES[tone])}>
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

/** Synthetic/demo data uses the spec's "mock" status colour. */
export function SyntheticTag() {
  return (
    <Badge tone="mock" icon={<Info className="size-3" aria-hidden />}>
      Synthetic data
    </Badge>
  );
}

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center justify-center gap-2 py-12 text-sm text-ink-muted">
      <Loader2 className="size-4 animate-spin text-primary" aria-hidden />
      {label}
    </div>
  );
}

export function SkeletonGrid({ count = 4 }: { count?: number }) {
  return (
    <div role="status" aria-label="Loading" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="h-28 animate-pulse rounded-lg border border-outline bg-surface-soft/60" />
      ))}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError | { message: string; requestId?: string }; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-lg border border-danger/30 bg-status-danger-bg/60 p-5 text-sm">
      <div className="flex items-start gap-3">
        <XCircle className="mt-0.5 size-5 shrink-0 text-danger" aria-hidden />
        <div className="flex-1">
          <p className="font-semibold text-danger-ink">Something went wrong</p>
          <p className="mt-1 text-ink">{error.message}</p>
          {"requestId" in error && error.requestId && <p className="mt-1 font-mono text-xs text-ink-muted">Reference: {error.requestId}</p>}
        </div>
        {onRetry && (
          <Button variant="secondary" onClick={onRetry} className="h-8 px-3 text-xs">
            <RefreshCw className="size-3" aria-hidden /> Retry
          </Button>
        )}
      </div>
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-outline-strong px-6 py-10 text-center">
      <Inbox className="size-8 text-ink-muted" aria-hidden />
      <p className="mt-3 text-sm font-semibold text-ink">{title}</p>
      {children && <div className="mt-1 max-w-md text-sm text-ink-muted">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warn"; children: ReactNode }) {
  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-md border p-3 text-sm",
        tone === "warn" ? "border-warning/40 bg-status-mock-bg/60 text-ink" : "border-primary/25 bg-primary/5 text-ink",
      )}
    >
      {tone === "warn" ? <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning-ink" aria-hidden /> : <Info className="mt-0.5 size-4 shrink-0 text-primary-ink" aria-hidden />}
      <div>{children}</div>
    </div>
  );
}

export function ProgressBar({ value, label }: { value: number; label: string }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)} className="h-2 w-full overflow-hidden rounded-full bg-surface-soft">
      <div className="h-full rounded-full bg-primary transition-[width] duration-300 ease-standard" style={{ width: `${pct}%` }} />
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
    primary: "bg-primary-ink text-white hover:bg-primary-ink/90 disabled:bg-outline-strong disabled:text-ink-muted",
    secondary: "border border-outline-strong bg-surface-elevated text-ink hover:border-primary hover:text-primary-ink disabled:text-ink-muted",
    ghost: "text-ink-muted hover:bg-primary/10 hover:text-primary-ink",
  }[variant];
  return (
    <button
      type="button"
      {...props}
      className={cn(
        "inline-flex h-10 items-center justify-center gap-1.5 rounded-sm px-4 text-sm font-medium transition-colors duration-150 ease-standard disabled:cursor-not-allowed",
        styles,
        className,
      )}
    >
      {children}
    </button>
  );
}

/** Neutral table base (spec: prefer neutral shadcn-style tables for general product surfaces). */
export const tableClasses = {
  table: "w-full text-left text-sm",
  head: "border-b border-outline text-xs font-semibold uppercase tracking-wider text-ink-muted",
  th: "h-12 px-2 font-semibold",
  row: "border-b border-outline last:border-0 transition-colors duration-150 hover:bg-primary/5",
  td: "px-2 py-2 text-ink-muted",
};
