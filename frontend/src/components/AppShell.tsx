import Link from "next/link";
import type { ReactNode } from "react";

export function AppShell({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <div className="min-h-screen bg-neutral-50 text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100">
      <header className="border-b border-neutral-200 dark:border-neutral-800">
        <nav
          aria-label="Main"
          className="mx-auto flex max-w-5xl items-center gap-6 px-6 py-4"
        >
          <span className="font-semibold tracking-tight">Governance</span>
          <Link href="/" className="text-sm text-neutral-600 hover:underline dark:text-neutral-300">
            Sessions
          </Link>
          <Link
            href="/agents"
            className="text-sm text-neutral-600 hover:underline dark:text-neutral-300"
          >
            Agents
          </Link>
        </nav>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-8">{children}</main>
    </div>
  );
}
