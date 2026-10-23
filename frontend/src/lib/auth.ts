// Browser-side auth helpers. Credentials are posted to our own route handler,
// which sets an httpOnly session cookie; the page never stores tokens.

export async function signIn(email: string, password: string): Promise<{ ok: true } | { ok: false; message: string }> {
  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: email.trim(), password }),
    });
    if (response.ok) return { ok: true };
    const body = await response.json().catch(() => null);
    return { ok: false, message: body?.error?.message ?? "Sign-in failed. Please try again." };
  } catch {
    return { ok: false, message: "Network error. Check your connection and try again." };
  }
}

export async function signOut(): Promise<void> {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } finally {
    window.localStorage.removeItem("exl.selectedCustomer");
    // Full reload on purpose: drops all in-memory client state after sign-out.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/login");
  }
}
