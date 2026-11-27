import "./globals.css";
import type { Metadata } from "next";
import { Inter } from "next/font/google";

const inter = Inter({ subsets: ["latin"], display: "swap" });

export const metadata: Metadata = {
  title: "ForgeAI · The agent that builds agents",
  description: "Engineer document-grounded AI agents with measured, honest quality evidence.",
  icons: { icon: "/mark.svg" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.className}>
      <body className="min-h-screen bg-canvas text-ink">{children}</body>
    </html>
  );
}
