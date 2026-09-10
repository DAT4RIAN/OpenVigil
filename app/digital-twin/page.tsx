import type { Metadata } from "next";

import { DigitalTwinPage } from "@/components/pages/digital-twin-page";
import { getProductionBackendConfig } from "@/lib/production-runtime";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "数字孪生",
  description: "OpenVigil 资产结构、SCADA、健康、告警与执行上下文运营孪生视图。",
};

export default function Page() {
  return <DigitalTwinPage runtimeMode={getProductionBackendConfig().mode} />;
}
