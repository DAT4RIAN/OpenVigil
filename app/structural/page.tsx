import type { Metadata } from "next";
import { StructuralPage } from "@/components/pages/structural-page";
import { getProductionBackendConfig } from "@/lib/production-runtime";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "混塔结构工作台",
  description: "结构观测、工程证据与受控复测的审核工作台。",
};

export default function Page() {
  return <StructuralPage runtimeMode={getProductionBackendConfig().mode} />;
}
