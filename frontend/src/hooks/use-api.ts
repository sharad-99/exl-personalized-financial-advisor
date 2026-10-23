"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError, apiGet } from "@/lib/api-client";

export interface ApiState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
}

/** Fetch a backend resource. Pass `null` as the path to wait (e.g. until a customer is selected). */
export function useApi<T>(path: string | null, params?: Record<string, string | number | undefined>): ApiState<T> {
  const [state, setState] = useState<{ data: T | null; error: ApiError | null; loading: boolean }>({
    data: null,
    error: null,
    loading: path !== null,
  });
  const [nonce, setNonce] = useState(0);
  const key = JSON.stringify(params ?? {});

  useEffect(() => {
    if (path === null) return;
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loading flag must reset when the request changes
    setState((s) => ({ ...s, loading: true, error: null }));
    apiGet<T>(path, JSON.parse(key))
      .then((data) => !cancelled && setState({ data, error: null, loading: false }))
      .catch((error: unknown) => {
        if (cancelled) return;
        const apiError = error instanceof ApiError ? error : new ApiError(0, "network_error", "Could not reach the server.");
        setState({ data: null, error: apiError, loading: false });
      });
    return () => {
      cancelled = true;
    };
  }, [path, key, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { ...state, reload };
}
