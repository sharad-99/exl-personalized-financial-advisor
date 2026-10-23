import { Suspense } from "react";

import { AppShell } from "@/components/layout/app-shell";
import { LoadingState } from "@/components/shared/ui";

// The shell reads the URL and the session at request time, so it streams in
// behind a Suspense boundary (required with Cache Components).
export default function AuthenticatedLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<LoadingState label="Loading…" />}>
      <AppShell>{children}</AppShell>
    </Suspense>
  );
}
