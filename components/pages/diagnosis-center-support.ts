import { type StatusTone } from "@/components/data-display/status-badge";
import {
  diagnosisRecords,
  sortDiagnosisRecords,
  type DiagnosisRecord,
  type DiagnosisStatus,
} from "@/lib/diagnosis-data";
import type { RiskLevel } from "@/lib/types";

export type StatusFilter = "all" | DiagnosisStatus;

export type RiskFilter = "all" | RiskLevel;

export interface DiagnosisResponse {
  readonly data: readonly DiagnosisRecord[];
  readonly meta: {
    readonly count: number;
    readonly total: number;
    readonly filteredTotal: number;
    readonly model: {
      readonly mode: string;
      readonly deterministic: boolean;
      readonly readOnly: boolean;
      readonly realInference: boolean;
      readonly notice: string;
    };
  };
}

export interface BenchmarkDiagnosisEnvelope {
  readonly data: readonly {
    readonly replay_run_id: string;
    readonly event: {
      readonly event_id: number;
      readonly farm: string;
      readonly logical_asset_id: string;
      readonly online_turbine_id: string;
    };
    readonly replay: {
      readonly status: string;
      readonly mode: string;
      readonly anchor_at: string;
      readonly time_rule_version: string;
      readonly time_semantics: string;
      readonly error: string | null;
    };
    readonly model: {
      readonly model_id: string | null;
      readonly name: string | null;
      readonly version: string | null;
      readonly kind: string | null;
      readonly artifact_sha256: string | null;
      readonly artifact_present: boolean;
    };
    readonly deployment: {
      readonly deployment_id: string | null;
      readonly status: string | null;
      readonly target_id: string | null;
      readonly stale: boolean;
      readonly threshold_policy_version: string | null;
      readonly threshold_policy_sha256: string | null;
    };
    readonly quality_report: {
      readonly status: string;
      readonly quality_rule_version: string | null;
      readonly feature_set_version: string | null;
      readonly mask_count: number;
      readonly mask_artifact: {
        readonly uri: string | null;
        readonly sha256: string | null;
        readonly present: boolean;
      };
    };
    readonly predictions: readonly {
      readonly prediction_id: string;
      readonly status: string;
      readonly error_code: string | null;
      readonly anomaly_score: number | null;
      readonly binary_prediction: boolean | null;
      readonly component: string | null;
      readonly model_id: string;
      readonly deployment_id: string;
      readonly evaluation_run_id: string | null;
      readonly feature_window: {
        readonly start: string | null;
        readonly end: string | null;
        readonly start_sequence: number | null;
        readonly end_sequence: number | null;
      };
      readonly threshold: {
        readonly value: number | null;
        readonly comparison: string | null;
        readonly policy_version: string | null;
        readonly policy_sha256: string | null;
      };
      readonly time_evidence: {
        readonly synthetic_observed_at: string;
        readonly observed_at_is_synthetic: boolean;
        readonly time_claim: string | null;
        readonly anonymous_observed_at: string | null;
        readonly source_time_stamp: string | number | null;
        readonly source_row_id: number | null;
      };
      readonly quality: {
        readonly signal_count: number;
        readonly signals_truncated: boolean;
        readonly quality_counts: Readonly<Record<string, number>>;
        readonly quality_mask_refs: readonly string[];
      };
      readonly evidence_artifact: {
        readonly uri: string | null;
        readonly sha256: string | null;
        readonly present: boolean;
      };
      readonly links: {
        readonly alarm_id: string | null;
        readonly alarm_status: string | null;
        readonly mission_id: string | null;
        readonly mission_status: string | null;
        readonly decision_id: string | null;
      };
    }[];
    readonly predictions_truncated: boolean;
    readonly first_alert: {
      readonly prediction_id: string;
      readonly alarm_id: string;
      readonly mission_id: string | null;
      readonly synthetic_observed_at: string;
      readonly anonymous_observed_at: string | null;
      readonly source_sequence: number;
      readonly lead_source_rows: number | null;
      readonly lead_semantics: "source-row-offset-not-rul";
    } | null;
    readonly truth: {
      readonly access: "restricted" | "revealed";
      readonly event_label: string | null;
      readonly event_interval_start: number | null;
      readonly event_interval_end: number | null;
      readonly description: string | null;
    };
  }[];
  readonly meta: {
    readonly count: number;
    readonly filtered_total: number;
    readonly truth_revealed: boolean;
    readonly truth_reveal_allowed: boolean;
    readonly bounds: {
      readonly diagnosis_page_max: number;
      readonly predictions_per_replay_max: number;
      readonly signals_inspected_per_prediction_max: number;
    };
  };
}

export const statusLabels: Readonly<Record<DiagnosisStatus, string>> = {
  triage: "待分诊",
  monitoring: "持续监测",
  analyzed: "诊断已形成",
  "awaiting-review": "人工复核中",
  "revision-needed": "方案待修订",
  rejected: "方案被拒绝",
  scheduled: "等待安全窗口",
  "in-progress": "受控作业中",
  closed: "验证闭环",
};

export const riskLabels: Readonly<Record<RiskLevel, string>> = {
  critical: "严重",
  high: "高",
  medium: "中",
  low: "低",
};

export const riskTone = (risk: RiskLevel): StatusTone =>
  risk === "critical"
    ? "critical"
    : risk === "high"
      ? "warning"
      : risk === "medium"
        ? "info"
        : "success";

export const statusTone = (status: DiagnosisStatus): StatusTone => {
  if (status === "closed") return "success";
  if (status === "in-progress" || status === "scheduled" || status === "analyzed") return "info";
  if (status === "rejected") return "critical";
  if (status === "monitoring") return "neutral";
  return "warning";
};

export const sourceLabels: Readonly<Record<string, string>> = {
  "scada-anomaly": "SCADA 异常检出",
  "alarm-correlation": "告警关联接入",
  "scheduled-health-scan": "定时健康扫描",
};

export const initialRecords = sortDiagnosisRecords(diagnosisRecords, "priority-desc");
