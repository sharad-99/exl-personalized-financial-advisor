import { ConfidenceBadge, FreshnessBadge, Notice } from "@/components/shared/ui";
import { formatDate } from "@/lib/formatting";
import type { Analytics } from "@/types/api";

/** Freshness, confidence and known data limitations, always shown next to figures. */
export function DataQualityPanel({ dq, compact = false }: { dq: Analytics["data_quality"]; compact?: boolean }) {
  const warnings = dq.issues.filter((i) => i.severity !== "info");
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-xs text-ink-3">
        <FreshnessBadge freshness={dq.freshness} days={dq.days_since_last_transaction} />
        <ConfidenceBadge level={dq.confidence} />
        <span>Latest transaction {formatDate(dq.latest_transaction_date)} · {dq.history_months} complete months of history</span>
      </div>
      {!compact && dq.confidence !== "high" && (
        <Notice tone="warn">
          <p className="font-medium text-ink">Some figures are limited</p>
          <ul className="mt-1 list-disc pl-5">
            {dq.confidence_reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
            {warnings.map((i) => (
              <li key={i.code}>{i.message}{i.count > 1 ? ` (${i.count})` : ""}</li>
            ))}
          </ul>
        </Notice>
      )}
    </div>
  );
}
