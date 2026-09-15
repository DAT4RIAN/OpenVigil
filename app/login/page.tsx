import type { Metadata } from "next";
import { LoginPage } from "@/components/pages/login-page";
import { getProductionBackendConfig } from "@/lib/production-runtime";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "登录",
  description: "登录 OpenVigil 风电智能运维平台，连接风场态势、诊断证据与运维决策。",
  robots: { index: false, follow: false },
};

export default function Login() {
  return <LoginPage runtimeMode={getProductionBackendConfig().mode} />;
}
