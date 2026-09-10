import type { Metadata } from "next";
import { MissionCenterPage } from "@/components/pages/mission-center-page";
import { getProductionBackendConfig } from "@/lib/production-runtime";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Mission 中心",
  description: "多 Agent 运维任务生命周期看板。",
};

export default function Page() {
  return <MissionCenterPage runtimeMode={getProductionBackendConfig().mode} />;
}
