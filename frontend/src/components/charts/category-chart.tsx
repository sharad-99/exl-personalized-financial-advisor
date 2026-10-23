"use client";

import { Bar, BarChart, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatMoney, formatPct, humanize } from "@/lib/formatting";
import type { Analytics } from "@/types/api";

/** Spending by category: sorted horizontal bars, single hue (magnitude, not identity). */
export function CategoryChart({ categories, limit = 8 }: { categories: Analytics["spending_by_category"]; limit?: number }) {
  const top = categories.slice(0, limit);
  const rest = categories.slice(limit);
  const rows = top.map((c) => ({ name: humanize(c.category), amount: Number(c.amount), share: c.share_pct, group: c.group }));
  if (rest.length) {
    const other = rest.reduce((sum, c) => sum + Number(c.amount), 0);
    rows.push({ name: `Other (${rest.length})`, amount: other, share: null, group: "other" });
  }
  return (
    <figure>
      <div style={{ height: rows.length * 34 + 16 }} aria-hidden>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 72, left: 0, bottom: 0 }} barCategoryGap={6}>
            <XAxis type="number" hide />
            <YAxis type="category" dataKey="name" width={110} tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "#44506a" }} />
            <Tooltip
              cursor={{ fill: "rgba(15,27,45,0.04)" }}
              formatter={(value) => [formatMoney(String(value)), "Spent"]}
              contentStyle={{ borderRadius: 8, borderColor: "#e3e7ee", fontSize: 12 }}
            />
            <Bar dataKey="amount" fill="#0d9488" radius={[0, 4, 4, 0]} maxBarSize={18}>
              <LabelList dataKey="amount" position="right" formatter={(v) => formatMoney(String(v))} style={{ fontSize: 11, fill: "#44506a" }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <details className="mt-2 text-xs text-ink-2">
        <summary className="cursor-pointer text-ink-3">Show as table</summary>
        <table className="mt-2 w-full text-left tabular-nums">
          <caption className="sr-only">Spending by category for the analysis period</caption>
          <thead className="text-ink-3">
            <tr>
              <th className="py-1 font-medium">Category</th>
              <th className="py-1 font-medium">Type</th>
              <th className="py-1 text-right font-medium">Amount</th>
              <th className="py-1 text-right font-medium">Share</th>
            </tr>
          </thead>
          <tbody>
            {categories.map((c) => (
              <tr key={c.category} className="border-t border-line">
                <td className="py-1">{humanize(c.category)}</td>
                <td className="py-1">{humanize(c.group)}</td>
                <td className="py-1 text-right">{formatMoney(c.amount)}</td>
                <td className="py-1 text-right">{formatPct(c.share_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
