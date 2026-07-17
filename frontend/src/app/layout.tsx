import type { Metadata } from "next";

import { AppShell } from "@/components/AppShell";
import { AuthGate } from "@/components/AuthGate";
import { QueryProvider } from "@/lib/queries/QueryProvider";

import "./globals.css";

export const metadata: Metadata = {
  title: "Governance Dashboard",
  description: "Operator dashboard for voice-agent governance",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <QueryProvider>
          <AppShell>
            <AuthGate>{children}</AuthGate>
          </AppShell>
        </QueryProvider>
      </body>
    </html>
  );
}
