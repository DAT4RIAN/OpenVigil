import type { Metadata } from "next";
import { PredictiveMaintenancePage } from "@/components/pages/predictive-maintenance-page";

export const metadata: Metadata = {
  title: "预测性维护",
  description: "64 台风机失效概率、剩余寿命、健康趋势与风险矩阵。",
};

export default function Page() {
  return <PredictiveMaintenancePage />;
}
