import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { ClientProvider } from "@/lib/preview/client-context";
import { UiPrefsProvider } from "@/lib/preview/ui-prefs";
import { AppShell } from "@/components/shell/AppShell";

// Inter matches the original prototype's typography.
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

export const metadata: Metadata = {
  title: "WorkWeave UI preview",
  description: "Workforce continuity platform: onboarding, work companion, shift handover and exit knowledge transfer. UI preview with synthetic data.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body>
        <ClientProvider>
          <UiPrefsProvider>
            <AppShell>{children}</AppShell>
          </UiPrefsProvider>
        </ClientProvider>
      </body>
    </html>
  );
}
