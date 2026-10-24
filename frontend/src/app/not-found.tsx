import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-3 px-4 text-center">
      <h1 className="text-2xl font-semibold text-ink">Page not found</h1>
      <p className="text-sm text-ink-muted">The page you are looking for does not exist.</p>
      <Link href="/dashboard" className="text-sm font-medium text-primary-ink hover:underline">Go to dashboard</Link>
    </main>
  );
}
