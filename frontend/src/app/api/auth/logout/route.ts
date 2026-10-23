import { NextResponse, type NextRequest } from "next/server";

import { serverConfig } from "@/lib/server/config";
import { clearLocalSession, isSameOrigin, supabaseForRequest } from "@/lib/server/session";

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) {
    return NextResponse.json({ error: { code: "forbidden", message: "Cross-site request rejected" } }, { status: 403 });
  }
  const response = NextResponse.json({ ok: true });
  if (serverConfig.authMode === "supabase") {
    await supabaseForRequest(request, response).auth.signOut();
  }
  clearLocalSession(response);
  return response;
}
