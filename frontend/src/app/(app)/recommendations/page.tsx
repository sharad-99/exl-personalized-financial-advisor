"use client";

import { useState } from "react";

import { RecommendationCard } from "@/components/recommendations/recommendation-card";
import { Button, EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/shared/ui";
import { useApi } from "@/hooks/use-api";
import { useSession } from "@/hooks/use-session";
import type { RecommendationList, RecommendationStatus } from "@/types/api";

const TABS: { label: string; status?: RecommendationStatus }[] = [
  { label: "All" },
  { label: "Active", status: "pending" },
  { label: "Accepted", status: "accepted" },
  { label: "Completed", status: "completed" },
  { label: "Dismissed", status: "dismissed" },
  { label: "Expired", status: "expired" },
];

export default function HistoryPage() {
  const { me, customerId } = useSession();
  const [tab, setTab] = useState(0);
  const [page, setPage] = useState(1);
  const list = useApi<RecommendationList>(customerId ? `customers/${customerId}/recommendations` : null, {
    status: TABS[tab].status,
    page,
    page_size: 10,
  });

  if (!customerId) return <EmptyState title="No customer selected" />;

  return (
    <div className="space-y-6">
      <PageHeader title="Recommendation history" subtitle="Every recommendation is stored with the evidence used at the time, so past advice stays explainable." />
      <div role="tablist" aria-label="Filter by status" className="flex flex-wrap gap-1 border-b border-outline">
        {TABS.map((t, i) => (
          <button
            key={t.label}
            role="tab"
            type="button"
            aria-selected={tab === i}
            onClick={() => {
              setTab(i);
              setPage(1);
            }}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${tab === i ? "border-primary text-primary-ink" : "border-transparent text-ink-muted hover:text-ink"}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {list.loading && <LoadingState />}
      {list.error && <ErrorState error={list.error} onRetry={list.reload} />}
      {list.data && list.data.items.length === 0 && <EmptyState title="Nothing here yet" />}
      <div className="space-y-4">
        {list.data?.items.map((r) => (
          <RecommendationCard key={r.id} rec={r} readOnly={me?.role !== "customer"} onChanged={list.reload} />
        ))}
      </div>
      {list.data && list.data.meta.total_pages > 1 && (
        <div className="flex items-center justify-between text-sm text-ink-muted">
          <Button variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
          <span>Page {list.data.meta.page} of {list.data.meta.total_pages}</span>
          <Button variant="secondary" disabled={page >= list.data.meta.total_pages} onClick={() => setPage((p) => p + 1)}>Next</Button>
        </div>
      )}
    </div>
  );
}
