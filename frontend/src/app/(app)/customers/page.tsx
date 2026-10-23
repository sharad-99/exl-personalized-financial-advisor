"use client";

import Link from "next/link";
import { useState } from "react";

import { CustomerProfile } from "@/components/customers/customer-profile";
import { Button, Card, EmptyState, ErrorState, LoadingState, PageHeader, SyntheticTag } from "@/components/shared/ui";
import { useApi } from "@/hooks/use-api";
import { useSession } from "@/hooks/use-session";
import { humanize } from "@/lib/formatting";
import type { CustomerSummary, Paginated } from "@/types/api";

const SEGMENTS = ["young_salaried", "family_goal_saver", "pre_retiree", "gig_worker", "high_spender", "debt_stressed", "new_to_bank", "stale_profile"];

export default function CustomersPage() {
  const { me, customerId } = useSession();
  if (me?.role === "customer") return customerId ? <CustomerProfile customerId={customerId} /> : null;
  return <CustomerDirectory />;
}

function CustomerDirectory() {
  const { selectCustomer } = useSession();
  const [search, setSearch] = useState("");
  const [segment, setSegment] = useState("");
  const [page, setPage] = useState(1);
  const list = useApi<Paginated<CustomerSummary>>("customers", { search: search || undefined, segment: segment || undefined, page, page_size: 20 });

  return (
    <div className="space-y-6">
      <PageHeader title="Customers" subtitle="Synthetic personas available to the demo analyst (read-only)." action={<SyntheticTag />} />
      <Card>
        <div className="mb-4 flex flex-col gap-3 sm:flex-row">
          <label className="flex-1 text-sm">
            <span className="sr-only">Search by name</span>
            <input value={search} onChange={(e) => { setSearch(e.target.value.slice(0, 60)); setPage(1); }} placeholder="Search by name…" className="w-full rounded-lg border border-line px-3 py-2" />
          </label>
          <label className="text-sm">
            <span className="sr-only">Persona segment</span>
            <select value={segment} onChange={(e) => { setSegment(e.target.value); setPage(1); }} className="w-full rounded-lg border border-line bg-white px-3 py-2 sm:w-56">
              <option value="">All segments</option>
              {SEGMENTS.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
            </select>
          </label>
        </div>
        {list.loading && <LoadingState />}
        {list.error && <ErrorState error={list.error} onRetry={list.reload} />}
        {list.data && list.data.items.length === 0 && <EmptyState title="No customers match" />}
        {list.data && list.data.items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-ink-3">
                <tr>
                  <th className="px-2 py-2 font-medium">Name</th>
                  <th className="px-2 py-2 font-medium">Segment</th>
                  <th className="px-2 py-2 font-medium">Income pattern</th>
                  <th className="px-2 py-2"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {list.data.items.map((c) => (
                  <tr key={c.id} className="border-t border-line">
                    <td className="px-2 py-2 font-medium">{c.display_name}</td>
                    <td className="px-2 py-2">{humanize(c.persona_segment)}</td>
                    <td className="px-2 py-2">{humanize(c.income_pattern)}</td>
                    <td className="px-2 py-2 text-right">
                      <Link href={`/customers/${c.id}`} onClick={() => selectCustomer(c)} className="text-teal-ink hover:underline">View profile</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {list.data && list.data.meta.total_pages > 1 && (
          <div className="mt-3 flex items-center justify-between text-sm text-ink-2">
            <Button variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
            <span>Page {list.data.meta.page} of {list.data.meta.total_pages} · {list.data.meta.total} customers</span>
            <Button variant="secondary" disabled={page >= list.data.meta.total_pages} onClick={() => setPage((p) => p + 1)}>Next</Button>
          </div>
        )}
      </Card>
    </div>
  );
}
