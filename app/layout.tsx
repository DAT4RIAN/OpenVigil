import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { headers } from "next/headers";
import { requireChatGPTUser, chatGPTSignOutPath } from "@/app/chatgpt-auth";
import { IdentityProvider } from "@/components/providers/identity-provider";
import { QueryProvider } from "@/components/providers/query-provider";
import {
  decodeTrustedSession,
  TRUSTED_SESSION_HEADER,
  type WindOpsIdentitySession,
} from "@/lib/identity-session";
import { getProductionBackendConfig } from "@/lib/production-runtime";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const themeBootstrap = `(() => {
  try {
    const stored = localStorage.getItem("windops-theme");
    const preference = stored === "dark" || stored === "system" ? stored : "light";
    const resolved = preference === "system" && matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : preference === "dark"
        ? "dark"
        : "light";
    document.documentElement.dataset.theme = resolved;
    document.documentElement.style.colorScheme = resolved;
  } catch {
    document.documentElement.dataset.theme = "light";
    document.documentElement.style.colorScheme = "light";
  }
})();`;

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host =
    requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host") ?? "localhost:3000";
  const forwardedProtocol = requestHeaders.get("x-forwarded-proto");
  const protocol =
    forwardedProtocol === "http" || forwardedProtocol === "https"
      ? forwardedProtocol
      : host.startsWith("localhost")
        ? "http"
        : "https";
  const origin = `${protocol}://${host}`;
  const socialImage = new URL("/og.png", origin).toString();
  const description =
    "AI 原生的风电场智能运维控制中心：从 SCADA 异常发现、多 Agent 协同诊断，到人工审批与工单执行。";

  return {
    metadataBase: new URL(origin),
    title: {
      default: "WindOps 多智能体运维平台",
      template: "%s · WindOps",
    },
    description,
    openGraph: {
      type: "website",
      title: "WindOps · AI 原生风场智能运维",
      description,
      images: [
        { url: socialImage, width: 1536, height: 1024, alt: "WindOps 风电运维多智能体平台" },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: "WindOps · AI 原生风场智能运维",
      description,
      images: [socialImage],
    },
  };
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const runtime = getProductionBackendConfig();
  let session: WindOpsIdentitySession | null = null;
  if (runtime.mode === "production") {
    const user = await requireChatGPTUser("/");
    const requestHeaders = await headers();
    const backendSession = decodeTrustedSession(
      requestHeaders.get(TRUSTED_SESSION_HEADER),
      user.userId,
    );
    if (!backendSession) {
      return (
        <html lang="zh-CN">
          <body>
            <main className="root-session-gate" role="alert">
              <strong>WindOps Production</strong>
              <h1>生产身份会话不可用</h1>
              <p>可信 capability 会话缺失或无效，业务页面已安全停止。</p>
              <Link href="/">重新检查</Link>
            </main>
          </body>
        </html>
      );
    }
    session = {
      ...backendSession,
      displayName: user.displayName,
      signOutPath: chatGPTSignOutPath("/"),
    };
  }
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrap }} />
      </head>
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <IdentityProvider runtimeMode={runtime.mode} session={session}>
          <QueryProvider>{children}</QueryProvider>
        </IdentityProvider>
      </body>
    </html>
  );
}
