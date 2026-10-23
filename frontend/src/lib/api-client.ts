import type { ApiErrorBody } from "@/types/api";

// All requests go to the same-origin backend-for-frontend proxy, which adds
// the access token server-side. No tokens are handled in browser code.
const BASE = "/api/backend";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public requestId?: string,
  ) {
    super(message);
  }
}

async function parse<T>(response: Response): Promise<T> {
  const text = await response.text();
  const body = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const err = (body as ApiErrorBody | null)?.error;
    if (response.status === 401 && typeof window !== "undefined") {
      const next = encodeURIComponent(window.location.pathname);
      // Full reload on purpose: drops all in-memory client state when the session has expired.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.assign(`/login?next=${next}`);
    }
    throw new ApiError(response.status, err?.code ?? "error", err?.message ?? `Request failed (${response.status})`, err?.request_id);
  }
  return body as T;
}

export async function apiGet<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  const qs = query.toString();
  return parse<T>(await fetch(`${BASE}/${path}${qs ? `?${qs}` : ""}`, { cache: "no-store" }));
}

export async function apiSend<T>(method: "POST" | "PATCH", path: string, body?: unknown): Promise<T> {
  return parse<T>(
    await fetch(`${BASE}/${path}`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  );
}
