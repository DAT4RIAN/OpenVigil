import type { Metadata } from "next";
import { DecisionCenterPage } from "@/components/pages/decision-center-page";

export const metadata: Metadata = { title: "Decision Center", description: "可解释的 AI 运维方案比较与人工审批。" };

export default function Page() { return <DecisionCenterPage />; }

