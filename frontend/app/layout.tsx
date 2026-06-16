import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Rappi Ops Copilot",
  description: "Custom analytics chat interface for Rappi operations metrics.",
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
