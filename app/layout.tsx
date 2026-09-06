import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { headers } from "next/headers";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host") ?? "localhost:3000";
  const forwardedProtocol = requestHeaders.get("x-forwarded-proto");
  const protocol = forwardedProtocol === "http" || forwardedProtocol === "https"
    ? forwardedProtocol
    : host.startsWith("localhost")
      ? "http"
      : "https";
  const origin = `${protocol}://${host}`;
  const socialImage = new URL("/og.png", origin).toString();
  const description = "AI 原生的风电场智能运维控制中心：从 SCADA 异常发现、多 Agent 协同诊断，到人工审批与工单执行。";

  return {
    metadataBase: new URL(origin),
    title: {
      default: "WindOps Multi-Agent Platform",
      template: "%s · WindOps",
    },
    description,
    openGraph: {
      type: "website",
      title: "WindOps · AI-Native Operations for Wind Farms",
      description,
      images: [{ url: socialImage, width: 1536, height: 1024, alt: "WindOps 风电运维多智能体平台" }],
    },
    twitter: {
      card: "summary_large_image",
      title: "WindOps · AI-Native Operations for Wind Farms",
      description,
      images: [socialImage],
    },
  };
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
