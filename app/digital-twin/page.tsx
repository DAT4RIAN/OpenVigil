import type { Metadata } from "next";

import { DigitalTwinPage } from "@/components/pages/digital-twin-page";

export const metadata: Metadata = {
  title: "数字孪生",
  description: "WindOps 资产结构、SCADA、健康、告警与执行上下文运营孪生视图。",
};

export default function Page() {
  return <DigitalTwinPage />;
}
