import { NextResponse, type NextRequest } from "next/server";

import { SESSION_COOKIE, serverConfig } from "@/lib/server/config";
import { supabaseForRequest } from "@/lib/server/session";

// Optimistic gate only: send visitors without a session to /login. Real
// authentication and authorisation happen in the FastAPI backend on every call.
export async function proxy(request: NextRequest) {
  const response = NextResponse.next();
  let signedIn: boolean;
  if (serverConfig.authMode === "supabase") {
    const { data } = await supabaseForRequest(request, response).auth.getUser(); // also refreshes cookies
    signedIn = Boolean(data.user);
  } else {
    signedIn = Boolean(request.cookies.get(SESSION_COOKIE)?.value);
  }
  if (!signedIn) {
    const url = new URL("/login", request.url);
    url.searchParams.set("next", request.nextUrl.pathname);
    return NextResponse.redirect(url);
  }
  return response;
}

export const config = {
  matcher: ["/dashboard/:path*", "/customers/:path*", "/insights/:path*", "/goals/:path*", "/recommendations/:path*", "/settings/:path*"],
};
