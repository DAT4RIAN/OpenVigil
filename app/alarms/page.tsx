import type { Metadata } from "next";
import { AlarmCenterPage } from "@/components/pages/alarm-center-page";

export const metadata: Metadata = { title: "告警中心", description: "工业告警分级、关联分析与 AI 诊断。" };

export default function Page() { return <AlarmCenterPage />; }

