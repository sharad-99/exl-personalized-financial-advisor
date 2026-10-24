"use client";

import Link from "next/link";
import { useState } from "react";

import { CategoryChart } from "@/components/charts/category-chart";
import { CashFlowChart } from "@/components/charts/cash-flow-chart";
import { DataQualityPanel } from "@/components/dashboard/data-quality-panel";
import { GoalProgressList } from "@/components/goals/goal-progress-list";
import { RecommendationCard } from "@/components/recommendations/recommendation-card";
import { Card, EmptyState, ErrorState, PageHeader, SkeletonGrid, StatTile, SyntheticTag } from "@/components/shared/ui";
import { useApi } from "@/hooks/use-api";
import { useSession } from "@/hooks/use-session";
import { formatDate, formatMoney, formatPct, humanize } from "@/lib/formatting";
import type { Analytics, RecommendationList } from "@/types/api";

const PERIODS = [3, 6, 12] as const;

export default function DashboardPage() {
  const { me, customerId, customerName } = useSession();
  const [months, setMonths] = useState<number>(6);
  const analytics = useApi<Analytics>(customerId ? `customers/${customerId}/analytics` : null, { months });
  const recs = useApi<RecommendationList>(customerId ? `customers/${customerId}/recommendations` : null, { status: "pending", page_size: 3 });

  if (!customerId) return <EmptyState title="No customer selected">Choose a customer from the picker above.</EmptyState>;

  const a = analytics.data;
  const net = a ? Number(a.monthly_averages.net_observed_cash_flow ?? 0) : 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title={me?.role === "advisor" ? `${customerName}'s dashboard` : "Your financial dashboard"}
        subtitle={a ? `Averages over ${a.period.months_with_data} of ${a.period.months_in_period} complete months (${formatDate(a.period.start_date)} – ${formatDate(a.period.end_date)})` : "Computed from your transactions"}
        action={
          <div className="flex items-center gap-3">
            <SyntheticTag />
            <div role="group" aria-label="Analysis period" className="inline-flex rounded-sm border border-outline bg-surface-elevated p-0.5">
              {PERIODS.map((m) => (
                <button key={m} type="button" aria-pressed={months === m} onClick={() => setMonths(m)} className={`rounded-md px-3 py-1 text-sm ${months === m ? "bg-primary-ink text-white" : "text-ink-muted hover:bg-surface-soft/60"}`}>
                  {m}M
                </button>
              ))}
            </div>
          </div>
        }
      />

      {analytics.loading && <SkeletonGrid />}
      {analytics.error && <ErrorState error={analytics.error} onRetry={analytics.reload} />}

      {a && (
        <>
          <DataQualityPanel dq={a.data_quality} />
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile label="Avg monthly income" value={formatMoney(a.monthly_averages.income)} hint={a.income_stability.pattern === "variable" ? "Income varies month to month" : `${a.monthly_averages.basis_months} months observed`} />
            <StatTile label="Avg monthly expenses" value={formatMoney(a.monthly_averages.expenses)} hint={`Essentials ${formatMoney(a.monthly_averages.essential_expenses)}`} />
            <StatTile label="Net observed cash flow" value={formatMoney(a.monthly_averages.net_observed_cash_flow)} tone={a.monthly_averages.net_observed_cash_flow === null ? "neutral" : net >= 0 ? "good" : "bad"} hint="Per month; not guaranteed spare money" />
            <StatTile label="Savings rate" value={formatPct(a.savings_rate.value_pct)} hint={a.savings_rate.reason ?? "Of income, over the period"} />
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <Card title="Income vs expenses by month" className="lg:col-span-2">
              <CashFlowChart trend={a.monthly_trend} />
            </Card>
            <Card title="Emergency fund">
              {a.emergency_fund.status === "unknown" ? (
                <p className="text-sm text-ink-muted">{a.emergency_fund.reason}</p>
              ) : (
                <div className="space-y-2">
                  <p className="text-3xl font-semibold tabular-nums">{a.emergency_fund.coverage_months} <span className="text-base font-normal text-ink-muted">months covered</span></p>
                  <p className="text-sm text-ink-muted">Target: {a.emergency_fund.target_months} months of essential expenses ({formatMoney(a.emergency_fund.target_amount)})</p>
                  <p className="text-sm text-ink-muted">Liquid balance (reported): {formatMoney(a.emergency_fund.liquid_balance)}</p>
                  {a.emergency_fund.gap_amount && Number(a.emergency_fund.gap_amount) > 0 && <p className="text-sm font-medium text-warning-ink">Gap: {formatMoney(a.emergency_fund.gap_amount)}</p>}
                </div>
              )}
              <div className="mt-4 border-t border-outline pt-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">Estimated monthly capacity</p>
                <p className="mt-1 text-lg font-semibold tabular-nums">{formatMoney(a.savings_capacity.estimated_monthly_capacity)}</p>
                <p className="text-xs text-ink-muted">{a.savings_capacity.reason ?? "After essential spending and a provision for non-monthly obligations. An estimate, not guaranteed."}</p>
              </div>
            </Card>
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <Card title="Where the money went" className="lg:col-span-2">
              {a.spending_by_category.length ? <CategoryChart categories={a.spending_by_category} /> : <EmptyState title="No spending in this period" />}
            </Card>
            <Card title="Goal progress" action={<Link href="/goals" className="text-sm text-primary-ink hover:underline">Manage</Link>}>
              {a.goals.length ? <GoalProgressList goals={a.goals} /> : <EmptyState title="No goals yet" action={<Link href="/goals" className="text-sm text-primary-ink hover:underline">Create a goal</Link>} />}
            </Card>
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <Card title="Top recommendations" className="lg:col-span-2" action={<Link href="/insights" className="text-sm text-primary-ink hover:underline">Open money coach</Link>}>
              {recs.loading && <p className="text-sm text-ink-muted">Loading…</p>}
              {recs.error && <ErrorState error={recs.error} onRetry={recs.reload} />}
              {recs.data && recs.data.items.length === 0 && <EmptyState title="No open recommendations">Nothing needs your attention right now.</EmptyState>}
              <div className="space-y-3">
                {recs.data?.items.map((r) => (
                  <RecommendationCard key={r.id} rec={r} readOnly={me?.role !== "customer"} compact onChanged={recs.reload} />
                ))}
              </div>
            </Card>
            <Card title="Upcoming in the next 30 days">
              {a.upcoming_obligations.items.length === 0 ? (
                <p className="text-sm text-ink-muted">No known obligations due.</p>
              ) : (
                <ul className="divide-y divide-outline text-sm">
                  {a.upcoming_obligations.items.map((o) => (
                    <li key={o.obligation_id} className="flex justify-between gap-2 py-2">
                      <span>
                        {o.name}
                        <span className="block text-xs text-ink-muted">{formatDate(o.due_date)} · {humanize(o.frequency)}</span>
                      </span>
                      <span className="tabular-nums">{formatMoney(o.amount)}</span>
                    </li>
                  ))}
                  <li className="flex justify-between py-2 font-medium">
                    <span>Total</span>
                    <span className="tabular-nums">{formatMoney(a.upcoming_obligations.total_due)}</span>
                  </li>
                </ul>
              )}
            </Card>
          </div>
          <p className="text-xs text-ink-muted">{a.totals.note} Internal transfers ({formatMoney(a.totals.excluded_internal_transfers)}) and probable duplicates ({formatMoney(a.totals.excluded_duplicates)}) are excluded from totals.</p>
        </>
      )}
    </div>
  );
}
