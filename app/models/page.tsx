import type { Metadata } from "next";

import { ModelManagementPage } from "@/components/pages/model-management-page";

export const metadata: Metadata = {
  title: "模型管理",
  description: "WindOps 确定性模型能力、版本、输入输出、指标与真实边界注册表。",
};

export default function Page() {
  return <ModelManagementPage />;
}
