"use client";

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatCompactMoney, formatMoney, formatMonth } from "@/lib/formatting";
import type { Analytics } from "@/types/api";

// Validated pair (dataviz validator, light surface): teal + orange, CVD ΔE 10.7.
const INCOME = "#0d9488";
const EXPENSES = "#eb6834";

/** Monthly income vs expenses. One y-axis; net is shown in the tooltip and the table view. */
export function CashFlowChart({ trend }: { trend: Analytics["monthly_trend"] }) {
  const rows = trend.map((p) => ({
    month: formatMonth(p.month) + (p.is_partial ? " (MTD)" : ""),
    income: Number(p.income),
    expenses: Number(p.expenses),
    net: p.net_observed_cash_flow,
    hasData: p.has_data,
  }));
  return (
    <figure>
      <div className="h-72" aria-hidden>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} barGap={2} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="#eef1f5" />
            <XAxis dataKey="month" interval={0} tickLine={false} axisLine={{ stroke: "#d6dbe4" }} tick={{ fontSize: 12, fill: "#6b7489" }} />
            <YAxis tickFormatter={formatCompactMoney} tickLine={false} axisLine={false} width={64} tick={{ fontSize: 12, fill: "#6b7489" }} />
            <Tooltip
              cursor={{ fill: "rgba(15,27,45,0.04)" }}
              formatter={(value, name) => [formatMoney(String(value)), name === "income" ? "Income" : "Expenses"]}
              labelFormatter={(label, payload) => {
                const net = payload?.[0]?.payload?.net as string | undefined;
                return `${label}${net ? ` · Net ${formatMoney(net)}` : ""}`;
              }}
              contentStyle={{ borderRadius: 8, borderColor: "#e3e7ee", fontSize: 12 }}
            />
            <Legend formatter={(v) => (v === "income" ? "Income" : "Expenses")} iconType="circle" wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="income" fill={INCOME} radius={[4, 4, 0, 0]} maxBarSize={22} />
            <Bar dataKey="expenses" fill={EXPENSES} radius={[4, 4, 0, 0]} maxBarSize={22} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <details className="mt-2 text-xs text-ink-2">
        <summary className="cursor-pointer text-ink-3">Show as table</summary>
        <table className="mt-2 w-full text-left tabular-nums">
          <caption className="sr-only">Monthly income, expenses and net observed cash flow</caption>
          <thead className="text-ink-3">
            <tr>
              <th className="py-1 font-medium">Month</th>
              <th className="py-1 text-right font-medium">Income</th>
              <th className="py-1 text-right font-medium">Expenses</th>
              <th className="py-1 text-right font-medium">Net</th>
            </tr>
          </thead>
          <tbody>
            {trend.map((p) => (
              <tr key={p.month} className="border-t border-line">
                <td className="py-1">{formatMonth(p.month)}{p.is_partial ? " (month to date)" : ""}{!p.has_data ? " — no data" : ""}</td>
                <td className="py-1 text-right">{formatMoney(p.income)}</td>
                <td className="py-1 text-right">{formatMoney(p.expenses)}</td>
                <td className="py-1 text-right">{formatMoney(p.net_observed_cash_flow)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
