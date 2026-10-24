import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "EXL Financial Wellness Coach", template: "%s · EXL Financial Wellness Coach" },
  description: "Personalised, explainable financial-wellness insights (synthetic-data demo).",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { themeColor: "#000000" };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en-IN">
      <body>{children}</body>
    </html>
  );
}
