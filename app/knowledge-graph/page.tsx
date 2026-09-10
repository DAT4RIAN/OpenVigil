import type { Metadata } from "next";

import { KnowledgeGraphPage } from "@/components/pages/knowledge-graph-page";
import { getProductionBackendConfig } from "@/lib/production-runtime";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "故障知识图谱",
  description: "设备、异常、失效模式、证据、决策与工单闭环的 Neo4j 知识图谱工作台。",
};

export default function Page() {
  return <KnowledgeGraphPage runtimeMode={getProductionBackendConfig().mode} />;
}
