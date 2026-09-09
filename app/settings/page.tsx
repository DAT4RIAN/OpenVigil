import type { Metadata } from "next";

import { SystemSettingsPage } from "@/components/pages/system-settings-page";

export const metadata: Metadata = {
  title: "系统设置",
  description: "WindOps 运行时、D1、WebSocket、身份、主题与数据策略诊断工作区。",
};

export default function Page() {
  return <SystemSettingsPage />;
}
