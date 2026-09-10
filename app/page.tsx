import type { Metadata } from "next";
import { DashboardPage } from "@/components/pages/dashboard-page";
import { getProductionBackendConfig } from "@/lib/production-runtime";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "运营指挥中心 · WindOps",
  description: "华东海上风电场实时运行态势与 AI 运维任务总览。",
};

export default function Home() {
  return <DashboardPage runtimeMode={getProductionBackendConfig().mode} />;
}
