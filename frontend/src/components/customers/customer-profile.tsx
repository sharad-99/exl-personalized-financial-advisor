"use client";

import { useState } from "react";

import { Badge, Button, Card, EmptyState, ErrorState, LoadingState, PageHeader, SyntheticTag } from "@/components/shared/ui";
import { useApi } from "@/hooks/use-api";
import { formatDate, formatMoney, humanize } from "@/lib/formatting";
import type { Analytics, CustomerDetail, Paginated, Transaction } from "@/types/api";

const COUNTED_TONE = { income: "good", expense: "neutral", refund: "info", excluded: "warn" } as const;

export function CustomerProfile({ customerId }: { customerId: string }) {
  const detail = useApi<CustomerDetail>(`customers/${customerId}`);
  const analytics = useApi<Analytics>(`customers/${customerId}/analytics`);
  const [page, setPage] = useState(1);
  const txns = useApi<Paginated<Transaction>>(`customers/${customerId}/transactions`, { page, page_size: 15 });

  if (detail.loading) return <LoadingState />;
  if (detail.error) return <ErrorState error={detail.error} onRetry={detail.reload} />;
  const d = detail.data;
  if (!d) return null;
  const fp = d.financial_profile;
  const a = analytics.data;

  return (
    <div className="space-y-6">
      <PageHeader title={d.display_name} subtitle="Financial profile" action={d.is_synthetic && <SyntheticTag />} />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Persona details">
          {fp ? (
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div><dt className="text-xs text-ink-muted">Segment</dt><dd>{humanize(fp.persona_segment)}</dd></div>
              <div><dt className="text-xs text-ink-muted">Income pattern</dt><dd>{humanize(fp.income_pattern)}</dd></div>
              <div><dt className="text-xs text-ink-muted">Declared monthly income</dt><dd className="tabular-nums">{fp.declared_monthly_income ? formatMoney(fp.declared_monthly_income) : <Badge tone="warn">Not provided</Badge>}</dd></div>
              <div><dt className="text-xs text-ink-muted">Age band</dt><dd>{fp.age_band ?? "—"}</dd></div>
              <div><dt className="text-xs text-ink-muted">Dependents</dt><dd>{fp.dependents ?? "—"}</dd></div>
              <div><dt className="text-xs text-ink-muted">City tier</dt><dd>{humanize(fp.city_tier)}</dd></div>
              <div><dt className="text-xs text-ink-muted">Risk preference</dt><dd>{humanize(fp.risk_preference)}</dd></div>
              <div><dt className="text-xs text-ink-muted">Profile confirmed</dt><dd>{formatDate(fp.profile_updated_at)}</dd></div>
            </dl>
          ) : (
            <p className="text-sm text-ink-muted">No financial profile on file.</p>
          )}
        </Card>

        <Card title="Income pattern">
          {a ? (
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between"><dt className="text-ink-muted">Observed avg income</dt><dd className="tabular-nums">{formatMoney(a.monthly_averages.income)}</dd></div>
              <div className="flex justify-between"><dt className="text-ink-muted">Months with income</dt><dd>{a.income_stability.months_with_income}</dd></div>
              <div className="flex justify-between"><dt className="text-ink-muted">Stability</dt><dd>{humanize(a.income_stability.pattern)}</dd></div>
              <div className="flex justify-between"><dt className="text-ink-muted">Variation (CV)</dt><dd>{a.income_stability.coefficient_of_variation ?? "—"}</dd></div>
            </dl>
          ) : analytics.error ? (
            <ErrorState error={analytics.error} onRetry={analytics.reload} />
          ) : (
            <LoadingState />
          )}
        </Card>

        <Card title="Transaction summary">
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between"><dt className="text-ink-muted">Transactions</dt><dd>{d.transaction_summary.transaction_count.toLocaleString("en-IN")}</dd></div>
            <div className="flex justify-between"><dt className="text-ink-muted">First</dt><dd>{formatDate(d.transaction_summary.first_transaction_date)}</dd></div>
            <div className="flex justify-between"><dt className="text-ink-muted">Latest</dt><dd>{formatDate(d.transaction_summary.last_transaction_date)}</dd></div>
          </dl>
        </Card>
      </div>

      <Card title="Accounts">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-outline text-xs uppercase tracking-wider text-ink-muted">
              <tr>
                <th className="px-2 py-2 font-medium">Account</th>
                <th className="px-2 py-2 font-medium">Type</th>
                <th className="px-2 py-2 text-right font-medium">Reported balance</th>
                <th className="px-2 py-2 font-medium">As of</th>
                <th className="px-2 py-2 text-right font-medium">Estimated from transactions</th>
              </tr>
            </thead>
            <tbody>
              {d.accounts.map((acc) => {
                const est = a?.balances.accounts.find((b) => b.account_id === acc.id);
                return (
                  <tr key={acc.id} className="border-t border-outline">
                    <td className="px-2 py-2">{acc.nickname} <span className="text-xs text-ink-muted">{acc.masked_number}</span></td>
                    <td className="px-2 py-2">{humanize(acc.account_type)}{acc.is_liquid && <span className="ml-1 text-xs text-ink-muted">(liquid)</span>}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{acc.current_balance ? formatMoney(acc.current_balance, true) : <Badge tone="warn">Not reported</Badge>}</td>
                    <td className="px-2 py-2">{formatDate(acc.balance_as_of)}{est?.balance_is_stale && <Badge tone="warn">Stale</Badge>}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-ink-muted">{est ? formatMoney(est.estimated_balance_from_transactions, true) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-ink-muted">Reported balances are actual account records. Estimates are reconstructed from transactions and may differ.</p>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Existing obligations">
          {d.obligations.length === 0 ? (
            <p className="text-sm text-ink-muted">No obligations recorded.</p>
          ) : (
            <ul className="divide-y divide-outline text-sm">
              {d.obligations.map((o) => (
                <li key={o.id} className="flex justify-between gap-3 py-2">
                  <span>
                    {o.name}
                    <span className="block text-xs text-ink-muted">
                      {humanize(o.frequency)} · next {formatDate(o.next_due_date)}
                      {o.outstanding_principal && ` · outstanding ${formatMoney(o.outstanding_principal)}`}
                      {o.interest_rate_apr && ` · ${o.interest_rate_apr}% APR`}
                    </span>
                  </span>
                  <span className="tabular-nums">{formatMoney(o.amount)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Financial goals">
          {d.goals.length === 0 ? (
            <p className="text-sm text-ink-muted">No goals yet.</p>
          ) : (
            <ul className="divide-y divide-outline text-sm">
              {d.goals.map((g) => (
                <li key={g.id} className="flex justify-between gap-3 py-2">
                  <span>{g.name}<span className="block text-xs text-ink-muted">{humanize(g.status)} · target {formatDate(g.target_date)}</span></span>
                  <span className="tabular-nums">{formatMoney(g.saved_amount)} / {formatMoney(g.target_amount)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title="Recent transactions">
        {txns.loading && <LoadingState />}
        {txns.error && <ErrorState error={txns.error} onRetry={txns.reload} />}
        {txns.data && txns.data.items.length === 0 && <EmptyState title="No transactions" />}
        {txns.data && txns.data.items.length > 0 && (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-outline text-xs uppercase tracking-wider text-ink-muted">
                  <tr>
                    <th className="px-2 py-2 font-medium">Date</th>
                    <th className="px-2 py-2 font-medium">Description</th>
                    <th className="px-2 py-2 font-medium">Category</th>
                    <th className="px-2 py-2 font-medium">Counted as</th>
                    <th className="px-2 py-2 text-right font-medium">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {txns.data.items.map((t) => (
                    <tr key={t.id} className="border-t border-outline">
                      <td className="whitespace-nowrap px-2 py-2">{formatDate(t.posted_on)}</td>
                      <td className="px-2 py-2">{t.merchant_name ?? t.description}</td>
                      <td className="px-2 py-2">{humanize(t.effective_category)}{t.category_source === "keyword_rule" && <span className="ml-1 text-xs text-ink-muted">(auto)</span>}</td>
                      <td className="px-2 py-2"><Badge tone={COUNTED_TONE[t.counted_as]}>{t.exclusion_reason ? humanize(t.exclusion_reason) : humanize(t.counted_as)}</Badge></td>
                      <td className={`py-2 text-right tabular-nums ${t.direction === "credit" ? "text-success-ink" : ""}`}>{t.direction === "credit" ? "+" : "−"}{formatMoney(t.amount, true)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-3 flex items-center justify-between text-sm text-ink-muted">
              <Button variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
              <span>Page {txns.data.meta.page} of {txns.data.meta.total_pages}</span>
              <Button variant="secondary" disabled={page >= txns.data.meta.total_pages} onClick={() => setPage((p) => p + 1)}>Next</Button>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
