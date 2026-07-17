"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const NAV_LINK_CLASSES =
  "rounded-[var(--radius-badge)] px-2 py-1 text-sm text-muted transition-colors hover:bg-surface-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand";
const NAV_LINK_ACTIVE_CLASSES = "font-semibold text-brand";

export function AppShell({ children }: Readonly<{ children: ReactNode }>) {
  const pathname = usePathname();

  const navLinkClassName = (href: string) =>
    pathname === href ? `${NAV_LINK_CLASSES} ${NAV_LINK_ACTIVE_CLASSES}` : NAV_LINK_CLASSES;
  const navLinkAriaCurrent = (href: string) => (pathname === href ? "page" : undefined);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border bg-surface shadow-[var(--shadow-card)]">
        <nav
          aria-label="Main"
          className="mx-auto flex max-w-5xl items-center gap-6 px-6 py-4"
        >
          <span className="font-semibold tracking-tight">Governance</span>
          <Link href="/" aria-current={navLinkAriaCurrent("/")} className={navLinkClassName("/")}>
            Sessions
          </Link>
          <Link
            href="/agents"
            aria-current={navLinkAriaCurrent("/agents")}
            className={navLinkClassName("/agents")}
          >
            Agents
          </Link>
        </nav>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-8">{children}</main>
    </div>
  );
}
