import type { Metadata } from "next";
import { WindFarmPage } from "@/components/pages/wind-farm-page";
import { getProductionBackendConfig } from "@/lib/production-runtime";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "风场概览",
  description: "风电场机组状态、健康与拓扑概览。",
};

export default function Page() {
  return <WindFarmPage runtimeMode={getProductionBackendConfig().mode} />;
}
