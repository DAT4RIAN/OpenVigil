import type { Metadata } from "next";
import { MissionCenterPage } from "@/components/pages/mission-center-page";

export const metadata: Metadata = { title: "Mission Center", description: "多 Agent 运维任务生命周期看板。" };

export default function Page() { return <MissionCenterPage />; }

