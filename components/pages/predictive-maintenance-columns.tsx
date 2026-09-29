import type { LegacyColumnDef } from "@tanstack/react-table/legacy";
import type { PredictiveAssessment } from "@/app/api/predictive-assessments/fixtures";
import { HealthBadge, StatusBadge } from "@/components/data-display/status-badge";
import { riskLabels, riskTone, trendLabels } from "./predictive-maintenance-support";
import styles from "./predictive-maintenance-page.module.css";

export const assessmentColumns: readonly LegacyColumnDef<PredictiveAssessment, unknown>[] = [
  {
    accessorKey: "priorityScore",
    header: "优先分",
    cell: ({ row }) => <span className={styles.rank}>{row.original.priorityScore.toFixed(1)}</span>,
  },
  {
    id: "asset",
    header: "机组 / 部件",
    accessorFn: (assessment) => `${assessment.turbineId} ${assessment.component}`,
    cell: ({ row }) => (
      <span>
        <strong>{row.original.turbineId}</strong>
        <small>{row.original.component}</small>
      </span>
    ),
  },
  {
    accessorKey: "componentHealth",
    header: "健康度",
    cell: ({ row }) => <HealthBadge score={row.original.componentHealth} />,
  },
  {
    accessorKey: "anomalyScore",
    header: "异常分数",
    cell: ({ row }) => (
      <span>
        <strong>{row.original.anomalyScore.toFixed(2)}</strong>
        <small>证据等级 {row.original.evidenceBand}/5</small>
      </span>
    ),
  },
  {
    accessorKey: "activeAlarmCount",
    header: "活跃告警",
    cell: ({ row }) => (
      <span>
        <strong>{row.original.activeAlarmCount}</strong>
        <small>权威告警记录</small>
      </span>
    ),
  },
  {
    accessorKey: "evidenceBand",
    header: "证据等级",
    cell: ({ row }) => (
      <span>
        <strong>{row.original.evidenceBand} / 5</strong>
        <small>{trendLabels[row.original.trend]}</small>
      </span>
    ),
  },
  {
    accessorKey: "matrixRisk",
    header: "矩阵风险",
    cell: ({ row }) => (
      <StatusBadge
        value={row.original.matrixRisk}
        label={riskLabels[row.original.matrixRisk]}
        tone={riskTone(row.original.matrixRisk)}
        compact
      />
    ),
  },
];
