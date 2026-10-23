"use client";

import { ErrorState } from "@/components/shared/ui";

export default function AppError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <ErrorState error={{ message: "This page failed to load. Please try again.", requestId: error.digest }} onRetry={reset} />;
}
