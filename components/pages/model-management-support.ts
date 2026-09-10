import { Activity, BarChart3, BrainCircuit, FileText, HeartPulse } from "lucide-react";

import { PLATFORM_SNAPSHOT_AT, modelRegistry, type ModelKind } from "@/lib/platform-admin-data";

import type { ModelEnvelope } from "./model-management-contracts";

export const predictiveInputSchema = JSON.stringify(
  {
    $schema: "https://json-schema.org/draft/2020-12/schema",
    type: "object",
    additionalProperties: false,
    required: ["turbine_id", "observed_at", "signals"],
    properties: {
      turbine_id: { type: "string" },
      turbine_model: { type: "string" },
      health_score: { type: "number" },
      active_alarm_count: { type: "integer", minimum: 0 },
      observed_at: { type: "string", format: "date-time" },
      signals: { type: "object", additionalProperties: { type: "number" } },
    },
  },
  null,
  2,
);

export const predictiveOutputSchema = JSON.stringify(
  {
    $schema: "https://json-schema.org/draft/2020-12/schema",
    type: "object",
    additionalProperties: false,
    required: [
      "component",
      "failure_probability_30d",
      "remaining_useful_life_days",
      "anomaly_score",
      "primary_finding",
    ],
    properties: {
      component: { type: "string" },
      component_health: { type: "number", minimum: 0, maximum: 100 },
      failure_probability_30d: { type: "number", minimum: 0, maximum: 100 },
      remaining_useful_life_days: { type: "number", minimum: 0 },
      anomaly_score: { type: "number", minimum: 0, maximum: 1 },
      primary_finding: { type: "string" },
      trend: { enum: ["improving", "stable", "declining"] },
    },
  },
  null,
  2,
);

export const initialEnvelope: ModelEnvelope = {
  data: modelRegistry,
  meta: {
    count: modelRegistry.length,
    total: modelRegistry.length,
    deterministic: true,
    readOnly: true,
    snapshotAt: PLATFORM_SNAPSHOT_AT,
    realInferenceCount: 0,
    embeddingBackedCount: 0,
    disclosure:
      "Registry availability describes demo capability, not the presence of trained weights or hosted inference.",
  },
};

export const kindLabels: Readonly<Record<ModelKind, string>> = {
  anomaly: "异常检测",
  predictive: "预测维护",
  health: "健康评分",
  retrieval: "知识检索",
  report: "报告生成",
};

export const kindIcons = {
  anomaly: Activity,
  predictive: BarChart3,
  health: HeartPulse,
  retrieval: BrainCircuit,
  report: FileText,
} as const;
