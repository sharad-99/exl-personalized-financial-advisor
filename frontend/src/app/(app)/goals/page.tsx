"use client";

import { Pencil, Plus } from "lucide-react";
import { useState } from "react";

import { GoalForm } from "@/components/goals/goal-form";
import { Badge, Button, Card, EmptyState, ErrorState, LoadingState, PageHeader, ProgressBar } from "@/components/shared/ui";
import { useApi } from "@/hooks/use-api";
import { useSession } from "@/hooks/use-session";
import { formatDate, formatMoney, humanize } from "@/lib/formatting";
import type { Goal, GoalWithPlan } from "@/types/api";

const PLAN_TONE = { achieved: "good", on_track: "good", behind: "warn", overdue: "bad", no_target_date: "neutral", inactive: "neutral" } as const;

export default function GoalsPage() {
  const { me, customerId } = useSession();
  const readOnly = me?.role !== "customer";
  const goals = useApi<GoalWithPlan[]>(customerId ? `customers/${customerId}/goals` : null);
  const [editing, setEditing] = useState<Goal | "new" | null>(null);

  if (!customerId) return <EmptyState title="No customer selected" />;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Financial goals"
        subtitle="Track progress and see a safe, assumption-based monthly plan for each goal."
        action={!readOnly && editing === null && <Button onClick={() => setEditing("new")}><Plus className="size-4" aria-hidden /> New goal</Button>}
      />
      {editing && (
        <Card title={editing === "new" ? "Create a goal" : `Edit "${editing.name}"`}>
          <GoalForm
            customerId={customerId}
            goal={editing === "new" ? undefined : editing}
            onCancel={() => setEditing(null)}
            onSaved={() => {
              setEditing(null);
              goals.reload();
            }}
          />
        </Card>
      )}
      {goals.loading && <LoadingState />}
      {goals.error && <ErrorState error={goals.error} onRetry={goals.reload} />}
      {goals.data && goals.data.length === 0 && (
        <EmptyState title="No goals yet" action={!readOnly && <Button onClick={() => setEditing("new")}>Create your first goal</Button>}>
          Goals help the coach tailor savings guidance to what matters to you.
        </EmptyState>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        {goals.data?.map(({ goal, plan }) => (
          <Card
            key={goal.id}
            title={goal.name}
            action={
              <div className="flex items-center gap-2">
                {plan && <Badge tone={PLAN_TONE[plan.plan_status]}>{humanize(plan.plan_status)}</Badge>}
                {!readOnly && (
                  <button type="button" onClick={() => setEditing(goal)} aria-label={`Edit ${goal.name}`} className="rounded-md p-1 text-ink-muted hover:bg-surface-soft">
                    <Pencil className="size-4" />
                  </button>
                )}
              </div>
            }
          >
            <p className="text-xs text-ink-muted">{humanize(goal.goal_type)} · Priority {goal.priority}</p>
            <div className="mt-3">
              <ProgressBar value={plan ? Number(plan.progress_pct) : 0} label={`${goal.name} progress`} />
            </div>
            <p className="mt-2 text-sm tabular-nums">
              <span className="font-semibold">{formatMoney(goal.saved_amount)}</span> <span className="text-ink-muted">of {formatMoney(goal.target_amount)}</span>
            </p>
            <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
              <div><dt className="text-xs text-ink-muted">Target date</dt><dd>{formatDate(goal.target_date)}</dd></div>
              <div><dt className="text-xs text-ink-muted">Planned / month</dt><dd className="tabular-nums">{formatMoney(goal.monthly_contribution)}</dd></div>
              <div><dt className="text-xs text-ink-muted">Needed / month</dt><dd className="tabular-nums">{formatMoney(plan?.required_monthly)}</dd></div>
              <div><dt className="text-xs text-ink-muted">Months left</dt><dd>{plan?.months_remaining ?? "—"}</dd></div>
            </dl>
            {plan && (
              <div className="mt-3 rounded-sm bg-surface-soft/60 p-3 text-sm text-ink-muted">
                <p>{plan.guidance}</p>
                <details className="mt-1 text-xs">
                  <summary className="cursor-pointer text-ink-muted">Calculation and assumptions</summary>
                  <ul className="mt-1 space-y-0.5 font-mono">
                    {Object.entries(plan.calculation).map(([k, v]) => (
                      <li key={k}>{humanize(k)}: {v}</li>
                    ))}
                  </ul>
                  <ul className="mt-1 list-disc pl-4">
                    {plan.assumptions.map((x) => (
                      <li key={x}>{x}</li>
                    ))}
                  </ul>
                </details>
              </div>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}
