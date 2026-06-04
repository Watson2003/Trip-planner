import "leaflet/dist/leaflet.css";
import "./globals.css";

import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "AI Road Trip Planner",
  description: "Plan routes, budget, weather, and AI suggestions for your next road trip.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
