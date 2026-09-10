import type { Metadata } from "next";
import { DiagnosisCenterPage } from "@/components/pages/diagnosis-center-page";
import { getProductionBackendConfig } from "@/lib/production-runtime";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "智能诊断中心",
  description: "OpenVigil 结构化差分诊断、证据引用、Agent 协作与人工门禁工作台。",
};

export default function Page() {
  return <DiagnosisCenterPage runtimeMode={getProductionBackendConfig().mode} />;
}
