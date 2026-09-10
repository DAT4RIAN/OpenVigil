import type { Metadata } from "next";
import { AssetHealthPage } from "@/components/pages/asset-health-page";
import { getProductionBackendConfig } from "@/lib/production-runtime";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "设备健康",
  description: "64 台风机健康矩阵、风险分布和子系统评估。",
};

export default function Page() {
  return <AssetHealthPage runtimeMode={getProductionBackendConfig().mode} />;
}
