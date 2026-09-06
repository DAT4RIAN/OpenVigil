import type { Metadata } from "next";
import { AgentControlPage } from "@/components/pages/agent-control-page";

export const metadata: Metadata = { title: "Agent Control Center", description: "风电运维专业 Agent 的状态、任务和可观测性。" };

export default function Page() { return <AgentControlPage />; }

