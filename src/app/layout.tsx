import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Toaster } from "@/components/ui/toaster";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AI-Enhanced BGP Autonomous Control Plane · Simulation",
  description:
    "Interactive simulation of the AI-Enhanced BGP autonomous control plane: 10-AS multi-tier topology, ML anomaly detection, behavioral trust scoring, shadow validation, autonomous rollback, and 6 attack scenarios — every subsystem toggleable and editable.",
  keywords: ["BGP", "network security", "anomaly detection", "machine learning", "route hijack", "simulation", "FRRouting", "autonomous control plane"],
  authors: [{ name: "AI-Enhanced BGP Simulation" }],
  icons: {
    icon: "https://z-cdn.chatglm.cn/z-ai/static/logo.svg",
  },
  openGraph: {
    title: "AI-Enhanced BGP Autonomous Control Plane",
    description: "10-AS BGP anomaly detection & mitigation simulation with live telemetry, ML trust scoring, and autonomous rollback.",
    siteName: "AI-Enhanced BGP Simulator",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-background text-foreground`}
      >
        {children}
        <Toaster />
      </body>
    </html>
  );
}
