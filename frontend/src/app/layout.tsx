import type { Metadata } from "next";

import { AppShell } from "@/components/AppShell";
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
          <AppShell>{children}</AppShell>
        </QueryProvider>
      </body>
    </html>
  );
}
