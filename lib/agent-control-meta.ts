import { BrainCircuit, ShieldCheck, Wrench } from "lucide-react";
import type { AgentLayer, AgentStatus } from "./types";

export const agentLayerMeta: Record<
  AgentLayer,
  { label: string; description: string; icon: typeof BrainCircuit; tone: string }
> = {
  decision: {
    label: "Decision Layer",
    description: "发现、分析与策略生成",
    icon: BrainCircuit,
    tone: "teal",
  },
  review: {
    label: "Review Layer",
    description: "安全、工程与经济审核",
    icon: ShieldCheck,
    tone: "amber",
  },
  execution: {
    label: "Execution Layer",
    description: "资源编排与现场执行",
    icon: Wrench,
    tone: "blue",
  },
};

export const agentStatusLabel: Record<AgentStatus, string> = {
  idle: "IDLE",
  thinking: "THINKING",
  working: "WORKING",
  waiting: "WAITING",
  reviewing: "REVIEWING",
  failed: "FAILED",
  offline: "OFFLINE",
};
