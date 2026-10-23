"use client";

import { Check, ChevronDown, Flag, X } from "lucide-react";
import { useState } from "react";

import { Badge, Button, ConfidenceBadge, cn } from "@/components/shared/ui";
import { ApiError, apiSend } from "@/lib/api-client";
import { formatDate, humanize } from "@/lib/formatting";
import type { FeedbackAction, FeedbackReason, Recommendation } from "@/types/api";

const PRIORITY_TONE = { high: "bad", medium: "warn", low: "neutral" } as const;
const STATUS_TONE = { pending: "teal", accepted: "good", dismissed: "neutral", completed: "good", expired: "neutral" } as const;
const CORRECTION_REASONS: { value: FeedbackReason; label: string }[] = [
  { value: "income_incorrect", label: "My income is wrong" },
  { value: "expense_incorrect", label: "My expenses are wrong" },
  { value: "transaction_miscategorized", label: "A transaction is miscategorised" },
  { value: "goal_outdated", label: "My goal details are out of date" },
  { value: "other", label: "Something else" },
];
const DISMISS_REASONS: { value: FeedbackReason; label: string }[] = [
  { value: "not_relevant", label: "Not relevant to me" },
  { value: "already_doing_this", label: "I'm already doing this" },
  { value: "cannot_afford", label: "I can't afford this right now" },
  { value: "other", label: "Other" },
];

function renderValue(value: unknown): string {
  if (value === null || value === undefined) return "not available";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

export function RecommendationCard({
  rec,
  readOnly,
  onChanged,
  compact = false,
}: {
  rec: Recommendation;
  readOnly: boolean;
  onChanged?: (updated: Recommendation) => void;
  compact?: boolean;
}) {
  const [showEvidence, setShowEvidence] = useState(false);
  const [mode, setMode] = useState<null | "dismiss" | "correct">(null);
  const [reason, setReason] = useState<FeedbackReason>("not_relevant");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string } | null>(null);

  async function send(action: FeedbackAction, reasonCode?: FeedbackReason) {
    setBusy(true);
    setMessage(null);
    try {
      const result = await apiSend<{ recommendation: Recommendation }>("POST", `recommendations/${rec.id}/feedback`, {
        action,
        reason_code: reasonCode ?? null,
        comment: comment.trim() || null,
      });
      setMode(null);
      setComment("");
      setMessage({ tone: "ok", text: action === "correction" ? "Thanks — your correction was recorded for review." : `Marked as ${result.recommendation.status}.` });
      onChanged?.(result.recommendation);
    } catch (err) {
      setMessage({ tone: "error", text: err instanceof ApiError ? err.message : "Could not save your feedback." });
    } finally {
      setBusy(false);
    }
  }

  const calculations = rec.evidence.calculations ?? {};
  const inputs = rec.evidence.inputs ?? {};
  const actionable = !readOnly && (rec.status === "pending" || rec.status === "accepted");

  return (
    <article className="rounded-xl border border-line bg-surface p-5" aria-labelledby={`rec-${rec.id}`}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={PRIORITY_TONE[rec.priority]}>{humanize(rec.priority)} priority</Badge>
        <Badge tone={STATUS_TONE[rec.status]}>{humanize(rec.status)}</Badge>
        <ConfidenceBadge level={rec.confidence} />
        <span className="ml-auto text-xs text-ink-3">{humanize(rec.category)}</span>
      </div>
      <h3 id={`rec-${rec.id}`} className="mt-3 text-base font-semibold text-ink">
        {rec.title}
      </h3>
      <p className="mt-1 text-sm text-ink-2">{rec.explanation}</p>
      <p className="mt-2 text-sm text-ink">
        <span className="font-medium">Why: </span>
        {rec.reason}
      </p>

      {!compact && rec.suggested_actions.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-3">Suggested next steps</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-ink-2">
            {rec.suggested_actions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </div>
      )}

      <button
        type="button"
        onClick={() => setShowEvidence((v) => !v)}
        aria-expanded={showEvidence}
        className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-teal-ink hover:underline"
      >
        <ChevronDown className={cn("size-4 transition-transform", showEvidence && "rotate-180")} aria-hidden />
        {showEvidence ? "Hide" : "Show"} the numbers and assumptions
      </button>
      {showEvidence && (
        <div className="mt-3 space-y-3 rounded-lg bg-slate-50 p-4 text-sm">
          <div>
            <p className="font-medium text-ink">Calculations</p>
            <dl className="mt-1 space-y-1">
              {Object.entries(calculations).map(([k, v]) => (
                <div key={k} className="grid gap-1 sm:grid-cols-[180px_1fr]">
                  <dt className="text-ink-3">{humanize(k)}</dt>
                  <dd className="font-mono text-xs text-ink-2 break-words">{renderValue(v)}</dd>
                </div>
              ))}
            </dl>
          </div>
          <div>
            <p className="font-medium text-ink">Inputs used</p>
            <dl className="mt-1 space-y-1">
              {Object.entries(inputs).map(([k, v]) => (
                <div key={k} className="grid gap-1 sm:grid-cols-[180px_1fr]">
                  <dt className="text-ink-3">{humanize(k)}</dt>
                  <dd className="font-mono text-xs text-ink-2 break-words">{renderValue(v)}</dd>
                </div>
              ))}
            </dl>
          </div>
          <div>
            <p className="font-medium text-ink">Assumptions and limitations</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-5 text-ink-2">
              {rec.assumptions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </div>
          <p className="text-xs text-ink-3">
            Priority: {rec.priority_reason} · Confidence: {rec.confidence_reason} · Rule {rec.rule_id} v{rec.rule_version} · Data as of {formatDate(rec.data_as_of)} · Evaluated {formatDate(rec.analytics_as_of)} · Updated {formatDate(rec.updated_at)}
          </p>
        </div>
      )}

      {actionable && (
        <div className="mt-4 flex flex-wrap gap-2">
          {rec.status === "pending" && rec.category === "goal_celebration" && (
            <Button onClick={() => void send("completed")} disabled={busy}>
              <Check className="size-4" aria-hidden /> Got it
            </Button>
          )}
          {rec.status === "pending" && rec.category !== "goal_celebration" && (
            <Button onClick={() => void send("accepted")} disabled={busy}>
              <Check className="size-4" aria-hidden /> I&apos;ll do this
            </Button>
          )}
          {rec.status === "accepted" && (
            <Button onClick={() => void send("completed")} disabled={busy}>
              <Check className="size-4" aria-hidden /> Mark done
            </Button>
          )}
          <Button variant="secondary" disabled={busy} onClick={() => { setMode(mode === "dismiss" ? null : "dismiss"); setReason("not_relevant"); }}>
            <X className="size-4" aria-hidden /> Dismiss
          </Button>
          <Button variant="ghost" disabled={busy} onClick={() => { setMode(mode === "correct" ? null : "correct"); setReason("income_incorrect"); }}>
            <Flag className="size-4" aria-hidden /> Something&apos;s wrong
          </Button>
        </div>
      )}
      {readOnly && rec.status === "pending" && <p className="mt-3 text-xs text-ink-3">Advisors have read-only access; only the customer can respond.</p>}

      {mode && (
        <form
          className="mt-3 space-y-3 rounded-lg border border-line p-4"
          onSubmit={(e) => {
            e.preventDefault();
            void send(mode === "dismiss" ? "dismissed" : "correction", reason);
          }}
        >
          <label className="block text-sm">
            <span className="font-medium">{mode === "dismiss" ? "Why are you dismissing this?" : "What looks wrong?"}</span>
            <select value={reason} onChange={(e) => setReason(e.target.value as FeedbackReason)} className="mt-1 block w-full rounded-lg border border-line bg-white px-3 py-2 text-sm">
              {(mode === "dismiss" ? DISMISS_REASONS : CORRECTION_REASONS).map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            <span className="font-medium">Comment (optional)</span>
            <textarea value={comment} maxLength={500} onChange={(e) => setComment(e.target.value)} rows={2} className="mt-1 block w-full rounded-lg border border-line px-3 py-2 text-sm" />
            <span className="text-xs text-ink-3">{comment.length}/500 · Please don&apos;t include account numbers or passwords.</span>
          </label>
          <div className="flex gap-2">
            <Button type="submit" disabled={busy}>Submit</Button>
            <Button variant="secondary" onClick={() => setMode(null)}>Cancel</Button>
          </div>
        </form>
      )}
      {message && (
        <p role="status" className={cn("mt-3 text-sm", message.tone === "ok" ? "text-good" : "text-bad")}>
          {message.text}
        </p>
      )}
    </article>
  );
}
