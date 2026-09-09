import type { Metadata } from "next";
import { MaintenancePlanPage } from "@/components/pages/maintenance-plan-page";

export const metadata: Metadata = {
  title: "维护计划",
  description: "由工单、天气窗口与运维资源确定性派生的只读维护排程。",
};

export default function Page() {
  return <MaintenancePlanPage />;
}
