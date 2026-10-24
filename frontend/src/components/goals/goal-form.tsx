"use client";

import { useState } from "react";

import { Button } from "@/components/shared/ui";
import { ApiError, apiSend } from "@/lib/api-client";
import { humanize, todayISO } from "@/lib/formatting";
import { GOAL_TYPES, validateGoal, type FieldErrors, type GoalFormValues } from "@/lib/validation";
import type { Goal } from "@/types/api";

const EMPTY: GoalFormValues = { name: "", goal_type: "emergency_fund", target_amount: "", saved_amount: "0", monthly_contribution: "", target_date: "", priority: "3" };

export function GoalForm({ customerId, goal, onSaved, onCancel }: { customerId: string; goal?: Goal; onSaved: () => void; onCancel: () => void }) {
  const [values, setValues] = useState<GoalFormValues>(
    goal
      ? {
          name: goal.name,
          goal_type: goal.goal_type,
          target_amount: goal.target_amount,
          saved_amount: goal.saved_amount,
          monthly_contribution: goal.monthly_contribution ?? "",
          target_date: goal.target_date ?? "",
          priority: String(goal.priority),
        }
      : EMPTY,
  );
  const [errors, setErrors] = useState<FieldErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = (key: keyof GoalFormValues) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setValues((v) => ({ ...v, [key]: e.target.value }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const found = validateGoal(values, todayISO());
    setErrors(found);
    if (Object.keys(found).length) return;
    setBusy(true);
    setServerError(null);
    const payload = {
      name: values.name.trim(),
      target_amount: values.target_amount,
      saved_amount: values.saved_amount || "0",
      monthly_contribution: values.monthly_contribution || null,
      target_date: values.target_date || null,
      priority: Number(values.priority),
    };
    try {
      if (goal) await apiSend("PATCH", `customers/${customerId}/goals/${goal.id}`, payload);
      else await apiSend("POST", `customers/${customerId}/goals`, { ...payload, goal_type: values.goal_type });
      onSaved();
    } catch (err) {
      setServerError(err instanceof ApiError ? err.message : "Could not save the goal.");
    } finally {
      setBusy(false);
    }
  }

  const field = (key: keyof GoalFormValues, label: string, input: React.ReactNode, hint?: string) => (
    <label className="block text-sm">
      <span className="font-medium text-ink">{label}</span>
      {input}
      {errors[key] ? (
        <span id={`${key}-error`} className="mt-1 block text-xs text-danger-ink">{errors[key]}</span>
      ) : (
        hint && <span className="mt-1 block text-xs text-ink-muted">{hint}</span>
      )}
    </label>
  );
  const inputClass = (key: string) => `mt-1 block w-full rounded-sm border px-3 py-2 text-sm ${errors[key] ? "border-danger" : "border-outline"}`;
  const aria = (key: string) => ({ "aria-invalid": Boolean(errors[key]), "aria-describedby": errors[key] ? `${key}-error` : undefined });

  return (
    <form onSubmit={submit} noValidate className="grid gap-4 sm:grid-cols-2">
      {field("name", "Goal name", <input value={values.name} onChange={set("name")} maxLength={80} className={inputClass("name")} {...aria("name")} />)}
      {field(
        "goal_type",
        "Type",
        <select value={values.goal_type} onChange={set("goal_type")} disabled={Boolean(goal)} className={inputClass("goal_type")} {...aria("goal_type")}>
          {GOAL_TYPES.map((t) => (
            <option key={t} value={t}>{humanize(t)}</option>
          ))}
        </select>,
      )}
      {field("target_amount", "Target amount (₹)", <input inputMode="decimal" value={values.target_amount} onChange={set("target_amount")} className={inputClass("target_amount")} {...aria("target_amount")} />)}
      {field("saved_amount", "Already saved (₹)", <input inputMode="decimal" value={values.saved_amount} onChange={set("saved_amount")} className={inputClass("saved_amount")} {...aria("saved_amount")} />)}
      {field("monthly_contribution", "Planned monthly contribution (₹)", <input inputMode="decimal" value={values.monthly_contribution} onChange={set("monthly_contribution")} className={inputClass("monthly_contribution")} {...aria("monthly_contribution")} />, "Optional")}
      {field("target_date", "Target date", <input type="date" value={values.target_date} onChange={set("target_date")} className={inputClass("target_date")} {...aria("target_date")} />, "Optional, but needed for a monthly plan")}
      {field(
        "priority",
        "Priority",
        <select value={values.priority} onChange={set("priority")} className={inputClass("priority")} {...aria("priority")}>
          {[1, 2, 3, 4, 5].map((p) => (
            <option key={p} value={p}>{p} {p === 1 ? "(highest)" : p === 5 ? "(lowest)" : ""}</option>
          ))}
        </select>,
      )}
      {serverError && <p role="alert" className="text-sm text-danger-ink sm:col-span-2">{serverError}</p>}
      <div className="flex gap-2 sm:col-span-2">
        <Button type="submit" disabled={busy}>{busy ? "Saving…" : goal ? "Save changes" : "Create goal"}</Button>
        <Button variant="secondary" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  );
}
