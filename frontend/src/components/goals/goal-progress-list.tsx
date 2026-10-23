import { Badge, ProgressBar } from "@/components/shared/ui";
import { formatDate, formatMoney, humanize } from "@/lib/formatting";
import type { Analytics } from "@/types/api";

const PLAN_TONE = { achieved: "good", on_track: "good", behind: "warn", overdue: "bad", no_target_date: "neutral", inactive: "neutral" } as const;

export function GoalProgressList({ goals }: { goals: Analytics["goals"] }) {
  return (
    <ul className="space-y-4">
      {goals.map((g) => (
        <li key={g.goal_id}>
          <div className="flex items-baseline justify-between gap-2 text-sm">
            <span className="font-medium text-ink">{g.name}</span>
            <Badge tone={PLAN_TONE[g.plan_status]}>{humanize(g.plan_status)}</Badge>
          </div>
          <div className="mt-2">
            <ProgressBar value={Number(g.progress_pct)} label={`${g.name} progress`} />
          </div>
          <p className="mt-1 text-xs text-ink-3 tabular-nums">
            {formatMoney(g.saved_amount)} of {formatMoney(g.target_amount)} ({Number(g.progress_pct).toFixed(0)}%)
            {g.target_date && ` · by ${formatDate(g.target_date)}`}
          </p>
        </li>
      ))}
    </ul>
  );
}
