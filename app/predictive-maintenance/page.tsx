import type { Metadata } from "next";
import { PredictiveMaintenancePage } from "@/components/pages/predictive-maintenance-page";
import { getProductionBackendConfig } from "@/lib/production-runtime";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "预测性维护",
  description: "64 台风机健康、异常、告警与维护优先级。",
};

export default function Page() {
  return <PredictiveMaintenancePage runtimeMode={getProductionBackendConfig().mode} />;
}
