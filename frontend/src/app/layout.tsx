import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";

import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: "EXL Financial Wellness Coach", template: "%s · EXL Financial Wellness Coach" },
  description: "Personalised, explainable financial-wellness insights (synthetic-data demo).",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { themeColor: "#0b2545" };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en-IN" className={inter.variable}>
      <body>{children}</body>
    </html>
  );
}
