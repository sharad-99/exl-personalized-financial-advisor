"use client";

import { ChevronDown, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useApi } from "@/hooks/use-api";
import { useSession } from "@/hooks/use-session";
import { humanize } from "@/lib/formatting";
import type { CustomerSummary, Paginated } from "@/types/api";

/** Advisor-only: choose which synthetic customer to view. */
export function CustomerPicker() {
  const { customerName, selectCustomer } = useSession();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const { data, loading } = useApi<Paginated<CustomerSummary>>(open ? "customers" : null, { page_size: 100, search: search || undefined });

  useEffect(() => {
    const close = (event: MouseEvent) => ref.current && !ref.current.contains(event.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  return (
    <div ref={ref} className="relative max-w-sm">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex h-9 w-full items-center justify-between gap-2 rounded-sm bg-white/10 px-3 text-left text-sm text-white transition-colors duration-150 hover:bg-white/15"
      >
        <span className="truncate">
          <span className="text-white/60">Viewing: </span>
          <span className="font-medium">{customerName ?? "Select a customer"}</span>
        </span>
        <ChevronDown className="size-4 text-white/60" aria-hidden />
      </button>
      {open && (
        <div className="absolute z-50 mt-1 w-full rounded-md border border-outline bg-surface-elevated text-ink shadow-dialog">
          <label className="flex items-center gap-2 border-b border-outline px-3 py-2">
            <Search className="size-4 text-ink-muted" aria-hidden />
            <span className="sr-only">Search customers</span>
            <input autoFocus value={search} onChange={(e) => setSearch(e.target.value.slice(0, 60))} placeholder="Search name…" className="w-full bg-transparent text-sm outline-none placeholder:text-ink-muted" />
          </label>
          <ul role="listbox" aria-label="Customers" className="max-h-72 overflow-y-auto py-1">
            {loading && <li className="px-3 py-2 text-sm text-ink-muted">Loading…</li>}
            {data?.items.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={c.display_name === customerName}
                  onClick={() => {
                    selectCustomer(c);
                    setOpen(false);
                  }}
                  className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-primary/5 aria-selected:bg-primary/10"
                >
                  <span>{c.display_name}</span>
                  <span className="text-xs text-ink-muted">{humanize(c.persona_segment)}</span>
                </button>
              </li>
            ))}
            {data && data.items.length === 0 && <li className="px-3 py-2 text-sm text-ink-muted">No matches</li>}
          </ul>
        </div>
      )}
    </div>
  );
}
