import type { Metadata } from "next";
import { WorkOrderPage } from "@/components/pages/work-order-page";

export const metadata: Metadata = { title: "工单中心", description: "AI 决策到现场运维执行的工单闭环。" };

export default function Page() { return <WorkOrderPage />; }

