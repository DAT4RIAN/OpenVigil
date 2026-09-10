import type { Metadata } from "next";
import { DecisionCenterPage } from "@/components/pages/decision-center-page";
import { getProductionBackendConfig } from "@/lib/production-runtime";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "决策中心",
  description: "可解释的 AI 运维方案比较与人工审批。",
};

export default function Page() {
  return <DecisionCenterPage runtimeMode={getProductionBackendConfig().mode} />;
}
