import type { Metadata } from "next";
import { AgentControlPage } from "@/components/pages/agent-control-page";
import { getProductionBackendConfig } from "@/lib/production-runtime";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Agent 控制中心",
  description: "风电运维专业 Agent 的状态、任务和可观测性。",
};

export default function Page() {
  return <AgentControlPage runtimeMode={getProductionBackendConfig().mode} />;
}
