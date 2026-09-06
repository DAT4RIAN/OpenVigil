import type { Metadata } from "next";
import { DashboardPage } from "@/components/pages/dashboard-page";

export const metadata: Metadata = {
  title: "Operations Command Center · WindOps",
  description: "华东海上风电场实时运行态势与 AI 运维任务总览。",
};

export default function Home() {
  return <DashboardPage />;
}

