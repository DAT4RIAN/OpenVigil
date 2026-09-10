import type { Metadata } from "next";

import { DataCenterPage } from "@/components/pages/data-center-page";
import { getProductionBackendConfig } from "@/lib/production-runtime";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "数据中心",
  description: "WindOps 资产层级、数据集目录、质量、新鲜度与保留策略工作区。",
};

export default function Page() {
  return <DataCenterPage runtimeMode={getProductionBackendConfig().mode} />;
}
