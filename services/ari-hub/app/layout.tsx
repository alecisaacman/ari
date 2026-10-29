import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import "./globals.css";
import "./hub.css";

export const metadata: Metadata = {
  title: "ARI",
  description: "ARI is the intelligence spine. ACE is the private local-first interface.",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "ARI"
  }
};

export const viewport: Viewport = {
  themeColor: "#0e0f12",
  viewportFit: "cover"
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
