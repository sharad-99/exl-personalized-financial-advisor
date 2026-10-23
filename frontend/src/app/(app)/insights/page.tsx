"use client";

import { RefreshCw } from "lucide-react";
import { useState } from "react";

import { DataQualityPanel } from "@/components/dashboard/data-quality-panel";
import { RecommendationCard } from "@/components/recommendations/recommendation-card";
import { Button, Card, EmptyState, ErrorState, LoadingState, Notice, PageHeader } from "@/components/shared/ui";
import { useApi } from "@/hooks/use-api";
import { useSession } from "@/hooks/use-session";
import { ApiError, apiSend } from "@/lib/api-client";
import { formatMoney, humanize } from "@/lib/formatting";
import type { Analytics, Recommendation, RecommendationList, RefreshResult } from "@/types/api";

export default function MoneyCoachPage() {
  const { me, customerId } = useSession();
  const readOnly = me?.role !== "customer";
  const recs = useApi<RecommendationList>(customerId ? `customers/${customerId}/recommendations` : null, { status: "pending", page_size: 50 });
  const accepted = useApi<RecommendationList>(customerId ? `customers/${customerId}/recommendations` : null, { status: "accepted", page_size: 50 });
  const analytics = useApi<Analytics>(customerId ? `customers/${customerId}/analytics` : null);
  const [refresh, setRefresh] = useState<RefreshResult | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [lastAction, setLastAction] = useState<string | null>(null);
  const handleChanged = (updated: Recommendation) => {
    setLastAction(`"${updated.title}" marked as ${updated.status}.`);
    recs.reload();
    accepted.reload();
  };

  async function reevaluate() {
    if (!customerId) return;
    setBusy(true);
    setRefreshError(null);
    try {
      setRefresh(await apiSend<RefreshResult>("POST", `customers/${customerId}/recommendations/refresh`));
      recs.reload();
      accepted.reload();
    } catch (err) {
      setRefreshError(err instanceof ApiError ? err.message : "Could not refresh recommendations.");
    } finally {
      setBusy(false);
    }
  }

  if (!customerId) return <EmptyState title="No customer selected" />;
  const a = analytics.data;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Money coach"
        subtitle="Personal insights with the reasons and numbers behind them."
        action={
          !readOnly && (
            <Button variant="secondary" onClick={() => void reevaluate()} disabled={busy}>
              <RefreshCw className={`size-4 ${busy ? "animate-spin" : ""}`} aria-hidden /> Re-check my data
            </Button>
          )
        }
      />
      {a && <DataQualityPanel dq={a.data_quality} />}
      {refreshError && <ErrorState error={{ message: refreshError }} />}
      {lastAction && (
        <div role="status" className="rounded-lg border border-green-200 bg-green-50 px-4 py-2 text-sm text-good">
          {lastAction}
        </div>
      )}
      {refresh && (
        <Notice>
          Re-checked against data as of {refresh.as_of}: {refresh.created} new, {refresh.updated} updated, {refresh.expired} no longer apply.
          {refresh.suppressed_rules.length > 0 && (
            <details className="mt-1">
              <summary className="cursor-pointer">Why some checks were skipped ({refresh.suppressed_rules.length})</summary>
              <ul className="mt-1 list-disc pl-5">
                {refresh.suppressed_rules.map((s) => (
                  <li key={s.rule_id}>
                    <span className="font-medium">{humanize(s.rule_id.toLowerCase())}</span>: {s.reason}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </Notice>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <h2 className="text-sm font-semibold text-ink">Needs your attention</h2>
          {recs.loading && <LoadingState label="Working out your recommendations…" />}
          {recs.error && <ErrorState error={recs.error} onRetry={recs.reload} />}
          {recs.data && recs.data.items.length === 0 && <EmptyState title="You're all caught up">There are no open recommendations right now.</EmptyState>}
          {recs.data?.items.map((r) => (
            <RecommendationCard key={r.id} rec={r} readOnly={readOnly} onChanged={handleChanged} />
          ))}
          {accepted.data && accepted.data.items.length > 0 && (
            <>
              <h2 className="pt-2 text-sm font-semibold text-ink">In progress</h2>
              {accepted.data.items.map((r) => (
                <RecommendationCard key={r.id} rec={r} readOnly={readOnly} compact onChanged={handleChanged} />
              ))}
            </>
          )}
        </div>
        <div className="space-y-4">
          <Card title="How this works">
            <ul className="list-disc space-y-1 pl-5 text-sm text-ink-2">
              <li>Every suggestion comes from a fixed, versioned rule applied to your own (synthetic) data — no AI guesswork.</li>
              <li>Open &ldquo;Show the numbers&rdquo; to see each input and calculation.</li>
              <li>We never suggest saving money already committed to essentials, never suggest loans, and never recommend specific investments.</li>
              <li>If data is missing or old, we ask for it instead of guessing.</li>
            </ul>
          </Card>
          {a && (
            <Card title="Your numbers at a glance">
              <dl className="space-y-2 text-sm">
                <div className="flex justify-between"><dt className="text-ink-2">Avg income</dt><dd className="tabular-nums">{formatMoney(a.monthly_averages.income)}</dd></div>
                <div className="flex justify-between"><dt className="text-ink-2">Avg expenses</dt><dd className="tabular-nums">{formatMoney(a.monthly_averages.expenses)}</dd></div>
                <div className="flex justify-between"><dt className="text-ink-2">Estimated capacity</dt><dd className="tabular-nums">{formatMoney(a.savings_capacity.estimated_monthly_capacity)}</dd></div>
                <div className="flex justify-between"><dt className="text-ink-2">Recurring subscriptions</dt><dd className="tabular-nums">{a.recurring_expenses.filter((r) => r.is_subscription).length}</dd></div>
              </dl>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
