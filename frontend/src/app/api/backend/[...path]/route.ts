import { NextResponse, type NextRequest } from "next/server";

import { serverConfig } from "@/lib/server/config";
import { getAccessToken, isSameOrigin } from "@/lib/server/session";

// Backend-for-frontend proxy. The browser never sees the access token or the
// backend URL; this handler attaches the token from the httpOnly session.
const ALLOWED_PATH = /^(me(\/consent)?|customers(\/[0-9a-f-]{36}(\/(transactions|analytics|goals(\/[0-9a-f-]{36})?|obligations|recommendations(\/refresh)?|data-quality-events))?)?|recommendations\/[0-9a-f-]{36}(\/feedback)?|recommendation-rules)$/;
const MAX_BODY_BYTES = 32_768;

function error(status: number, code: string, message: string) {
  return NextResponse.json({ error: { code, message } }, { status });
}

async function forward(request: NextRequest, ctx: RouteContext<"/api/backend/[...path]">) {
  const { path } = await ctx.params;
  const joined = path.join("/");
  if (!ALLOWED_PATH.test(joined)) return error(404, "not_found", "Unknown API path");
  if (request.method !== "GET" && !isSameOrigin(request)) return error(403, "forbidden", "Cross-site request rejected");

  const passthrough = NextResponse.next();
  const token = await getAccessToken(request, passthrough);
  if (!token) return error(401, "unauthenticated", "Please sign in");

  let body: string | undefined;
  if (request.method !== "GET") {
    body = await request.text();
    if (body.length > MAX_BODY_BYTES) return error(413, "payload_too_large", "Request body too large");
  }

  try {
    const upstream = await fetch(`${serverConfig.apiBaseUrl}/api/v1/${joined}${request.nextUrl.search}`, {
      method: request.method,
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(serverConfig.requestTimeoutMs),
    });
    const text = await upstream.text();
    const response = new NextResponse(text, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") ?? "application/json",
        "Cache-Control": "no-store",
        "X-Request-ID": upstream.headers.get("x-request-id") ?? "",
      },
    });
    // Carry over refreshed Supabase auth cookies, if any.
    for (const cookie of passthrough.cookies.getAll()) response.cookies.set(cookie);
    return response;
  } catch (err) {
    const timedOut = err instanceof Error && err.name === "TimeoutError";
    return timedOut
      ? error(504, "timeout", "The advisor service took too long to respond")
      : error(503, "service_unavailable", "The advisor service is unavailable");
  }
}

export const GET = forward;
export const POST = forward;
export const PATCH = forward;
