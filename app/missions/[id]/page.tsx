import type { Metadata } from "next";
import { MissionDetailPage } from "@/components/pages/mission-detail-page";

export const metadata: Metadata = { title: "MISSION-2026-0823", description: "WT-023 主轴承异常的多 Agent 协作、证据、决策与审批。" };

export default function Page() { return <MissionDetailPage />; }

