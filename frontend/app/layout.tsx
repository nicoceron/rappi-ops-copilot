import "@n8n/chat/style.css";
import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Rappi Ops Copilot",
  description: "Embedded n8n chat interface for Rappi operations analytics.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
