import { NextResponse, type NextRequest } from "next/server";

import { serverConfig } from "@/lib/server/config";
import { isSameOrigin, setLocalSession, supabaseForRequest } from "@/lib/server/session";
import { validateLogin } from "@/lib/validation";

function error(status: number, code: string, message: string) {
  return NextResponse.json({ error: { code, message } }, { status });
}

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) return error(403, "forbidden", "Cross-site request rejected");
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return error(400, "bad_request", "Invalid JSON body");
  }
  const { email, password } = (body ?? {}) as { email?: unknown; password?: unknown };
  const problems = validateLogin(String(email ?? ""), String(password ?? ""));
  if (Object.keys(problems).length) return error(422, "validation_error", Object.values(problems)[0]);

  if (serverConfig.authMode === "supabase") {
    const response = NextResponse.json({ ok: true });
    const supabase = supabaseForRequest(request, response);
    const { error: authError } = await supabase.auth.signInWithPassword({ email: String(email), password: String(password) });
    if (authError) return error(401, "unauthenticated", "Invalid email or password");
    return response;
  }

  try {
    const upstream = await fetch(`${serverConfig.apiBaseUrl}/api/v1/auth/local/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
      signal: AbortSignal.timeout(serverConfig.requestTimeoutMs),
      cache: "no-store",
    });
    const payload = await upstream.json();
    if (!upstream.ok) return NextResponse.json(payload, { status: upstream.status });
    const response = NextResponse.json({ ok: true });
    setLocalSession(response, payload.access_token, payload.expires_in);
    return response;
  } catch {
    return error(503, "service_unavailable", "The advisor service is unavailable. Is the backend running?");
  }
}
