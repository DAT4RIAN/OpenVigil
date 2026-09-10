import type { Metadata } from "next";

import { SystemSettingsPage } from "@/components/pages/system-settings-page";
import { getProductionBackendConfig } from "@/lib/production-runtime";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "系统设置",
  description: "WindOps 运行时、身份、事件流、备份恢复与数据策略治理工作区。",
};

export default function Page() {
  return <SystemSettingsPage runtimeMode={getProductionBackendConfig().mode} />;
}
