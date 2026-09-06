import type { Metadata } from "next";
import { TurbineDetailPage } from "@/components/pages/turbine-detail-page";

export const metadata: Metadata = { title: "WT-023 数字资产", description: "WT-023 机组健康、SCADA、告警与维护信息。" };

export default function Page() { return <TurbineDetailPage />; }

