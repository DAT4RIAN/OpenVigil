import type { Metadata } from "next";

import { KnowledgeBasePage } from "@/components/pages/knowledge-base-page";
import { getProductionBackendConfig } from "@/lib/production-runtime";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "知识库",
  description: "风电运维知识文档、故障案例与带来源引用的确定性检索预览。",
};

export default function Page() {
  return <KnowledgeBasePage runtimeMode={getProductionBackendConfig().mode} />;
}
