import { ResourceCenterPage } from "@/components/pages/resource-center-page";
import { getProductionBackendConfig } from "@/lib/production-runtime";

export const dynamic = "force-dynamic";

export default function ResourcesRoute() {
  return <ResourceCenterPage runtimeMode={getProductionBackendConfig().mode} />;
}
