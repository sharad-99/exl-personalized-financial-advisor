import "server-only";

import { createServerClient } from "@supabase/ssr";
import type { NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE, serverConfig } from "./config";

/** Supabase server client bound to a request/response cookie pair (route handlers and proxy). */
export function supabaseForRequest(request: NextRequest, response: NextResponse) {
  return createServerClient(serverConfig.supabaseUrl, serverConfig.supabasePublishableKey, {
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll: (cookies) => {
        for (const { name, value, options } of cookies) {
          response.cookies.set(name, value, options);
        }
      },
    },
  });
}

/**
 * Resolve the backend access token for this request. Local mode: the httpOnly
 * cookie set at login. Supabase mode: the user is validated with the Auth
 * server first, then the session's access token is used. The backend
 * re-verifies every token; this is not the security boundary.
 */
export async function getAccessToken(request: NextRequest, response: NextResponse): Promise<string | null> {
  if (serverConfig.authMode === "local") {
    return request.cookies.get(SESSION_COOKIE)?.value ?? null;
  }
  const supabase = supabaseForRequest(request, response);
  const { data: userData, error } = await supabase.auth.getUser();
  if (error || !userData.user) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

export function setLocalSession(response: NextResponse, token: string, maxAgeSeconds: number) {
  response.cookies.set(SESSION_COOKIE, token, {
    httpOnly: true,
    secure: serverConfig.secureCookies,
    sameSite: "lax",
    path: "/",
    maxAge: maxAgeSeconds,
  });
}

export function clearLocalSession(response: NextResponse) {
  response.cookies.set(SESSION_COOKIE, "", { httpOnly: true, secure: serverConfig.secureCookies, sameSite: "lax", path: "/", maxAge: 0 });
}

/** CSRF defence for cookie-authenticated state changes: require a same-origin request. */
export function isSameOrigin(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return false;
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}
