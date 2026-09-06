import type { Metadata } from "next";
import { ScadaPage } from "@/components/pages/scada-page";

export const metadata: Metadata = { title: "SCADA 实时监测", description: "工业时序测点、阈值、异常点与 AI 事件监测。" };

export default function Page() { return <ScadaPage />; }

