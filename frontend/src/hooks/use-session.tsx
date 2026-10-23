"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { ApiError, apiGet } from "@/lib/api-client";
import type { CustomerSummary, Me, Paginated } from "@/types/api";

const STORAGE_KEY = "exl.selectedCustomer";

interface SessionValue {
  me: Me | null;
  error: ApiError | null;
  loading: boolean;
  /** Customer whose data is shown. Customers: always themselves. Advisors: chosen in the picker. */
  customerId: string | null;
  customerName: string | null;
  selectCustomer: (customer: CustomerSummary) => void;
  refreshMe: () => void;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [selected, setSelected] = useState<{ id: string; name: string } | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const profile = await apiGet<Me>("me");
        if (cancelled) return;
        setMe(profile);
        if (profile.role === "customer" && profile.customer_id) {
          setSelected({ id: profile.customer_id, name: profile.display_name });
          return;
        }
        const stored = window.localStorage.getItem(STORAGE_KEY);
        if (stored) {
          setSelected(JSON.parse(stored));
          return;
        }
        const first = await apiGet<Paginated<CustomerSummary>>("customers", { page_size: 1 });
        if (!cancelled && first.items[0]) setSelected({ id: first.items[0].id, name: first.items[0].display_name });
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err : new ApiError(0, "network_error", "Could not reach the server."));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [nonce]);

  const selectCustomer = useCallback((customer: CustomerSummary) => {
    const value = { id: customer.id, name: customer.display_name };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    setSelected(value);
  }, []);

  const value = useMemo<SessionValue>(
    () => ({
      me,
      error,
      loading: !me && !error,
      customerId: selected?.id ?? null,
      customerName: selected?.name ?? null,
      selectCustomer,
      refreshMe: () => setNonce((n) => n + 1),
    }),
    [me, error, selected, selectCustomer],
  );
  return <SessionContext value={value}>{children}</SessionContext>;
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside SessionProvider");
  return value;
}
