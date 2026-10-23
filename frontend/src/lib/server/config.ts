import "server-only";

// Server-only configuration. API_BASE_URL is never exposed to the browser:
// all backend calls go through the /api/backend route handler.
export const serverConfig = {
  apiBaseUrl: (process.env.API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, ""),
  authMode: (process.env.AUTH_MODE === "supabase" ? "supabase" : "local") as "local" | "supabase",
  supabaseUrl: process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
  supabasePublishableKey: process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "",
  secureCookies: process.env.NODE_ENV === "production",
  requestTimeoutMs: 15_000,
};

export const SESSION_COOKIE = "exl_session";
