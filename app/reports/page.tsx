import { ReportCenterPage } from "@/components/pages/report-center-page";
import { getProductionBackendConfig } from "@/lib/production-runtime";

export const dynamic = "force-dynamic";

export default function ReportsRoute() {
  return <ReportCenterPage runtimeMode={getProductionBackendConfig().mode} />;
}
