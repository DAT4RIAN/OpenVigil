import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { headers } from "next/headers";
import { getChatGPTUser, chatGPTSignOutPath } from "@/app/chatgpt-auth";
import { LoginPage } from "@/components/pages/login-page";
import { IdentityProvider } from "@/components/providers/identity-provider";
import { QueryProvider } from "@/components/providers/query-provider";
import {
  decodeTrustedSession,
  TRUSTED_SESSION_HEADER,
  type OpenVigilIdentitySession,
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
    const current = localStorage.getItem("openvigil-theme");
    const stored = current ?? localStorage.getItem("windops-theme");
    if (current === null && stored !== null) localStorage.setItem("openvigil-theme", stored);
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
    "AI 原生的风电智能运维平台：从 SCADA 异常发现、多 Agent 协同诊断，到人工审批与工单执行。";

  return {
    metadataBase: new URL(origin),
    title: {
      default: "OpenVigil 多智能体运维平台",
      template: "%s · OpenVigil",
    },
    description,
    openGraph: {
      type: "website",
      title: "OpenVigil · AI 原生风场智能运维",
      description,
      images: [
        { url: socialImage, width: 1536, height: 1024, alt: "OpenVigil 风电运维多智能体平台" },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: "OpenVigil · AI 原生风场智能运维",
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
  let session: OpenVigilIdentitySession | null = null;
  let content = children;
  if (runtime.mode === "production") {
    const user = await getChatGPTUser();
    const requestHeaders = await headers();
    const backendSession = user
      ? decodeTrustedSession(requestHeaders.get(TRUSTED_SESSION_HEADER), user.userId)
      : null;
    if (user && backendSession) {
      session = {
        ...backendSession,
        displayName: user.displayName,
        signOutPath: chatGPTSignOutPath("/"),
      };
    } else {
      // Never render protected children with a missing or invalid capability session.
      content = <LoginPage runtimeMode="production" />;
    }
  }
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrap }} />
      </head>
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <IdentityProvider runtimeMode={runtime.mode} session={session}>
          <QueryProvider>{content}</QueryProvider>
        </IdentityProvider>
      </body>
    </html>
  );
}
