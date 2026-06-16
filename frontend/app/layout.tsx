import "./globals.css";
import "leaflet/dist/leaflet.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Rappi Ops Copilot",
  description: "Custom analytics chat interface for Rappi operations metrics.",
  icons: {
    icon: "/brand/rappi-ops-mark.svg",
    shortcut: "/brand/rappi-ops-mark.svg",
    apple: "/brand/rappi-ops-mark.svg",
  },
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
