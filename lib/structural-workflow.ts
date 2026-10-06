export interface StructuralPageData<T> {
  readonly items: readonly T[];
  readonly next_cursor: string | null;
}

export interface StructuralIdentity {
  readonly id: string;
  readonly code: string;
  readonly revision: string;
  readonly name?: string;
  readonly component_id?: string;
  readonly tendon_id?: string | null;
  readonly quantity?: string;
  readonly calibration_version?: string;
  readonly calibration_valid_until?: string;
}

export interface StructuralTopology {
  readonly components: StructuralPageData<StructuralIdentity>;
  readonly tendons: StructuralPageData<StructuralIdentity>;
  readonly sensors: StructuralPageData<StructuralIdentity>;
}

export interface StructuralEvidenceCard {
  readonly evidence_id: string;
  readonly reference: {
    readonly kind: string;
    readonly source_id: string;
    readonly relation: string;
    readonly quote?: string | null;
  };
  readonly turbine_id: string;
  readonly component_id: string;
  readonly time_window: Readonly<Record<string, string | null>>;
  readonly source: Readonly<Record<string, unknown>>;
  readonly method: Readonly<Record<string, unknown>>;
  readonly measurements: readonly {
    readonly name: string;
    readonly value: number | null;
    readonly unit: string;
  }[];
  readonly quality: Readonly<Record<string, unknown>>;
  readonly uncertainty: Readonly<Record<string, unknown>>;
  readonly applicability: Readonly<Record<string, unknown>>;
  readonly valid_until: string | null;
  readonly source_fingerprint: string;
}

export interface StructuralClaim {
  readonly id: string;
  readonly revision: number;
  readonly conclusion: string;
  readonly effective_status: string;
  readonly review_status: string;
  readonly created_by: string;
  readonly valid_until: string;
  readonly missing_evidence: readonly string[];
  readonly applicability: Readonly<Record<string, unknown>>;
  readonly evidence_cards: readonly StructuralEvidenceCard[];
  readonly reviews: readonly {
    readonly id: string;
    readonly action: string;
    readonly reason: string;
    readonly reviewed_by: string;
    readonly created_at: string;
  }[];
}

export interface StructuralContext {
  readonly mission_id: string;
  readonly revision: number;
  readonly claim_id: string | null;
  readonly scenario: "modal_frequency_review" | "prestress_retest";
  readonly status: string;
  readonly missing_evidence: readonly string[];
  readonly comparison: Readonly<Record<string, unknown>>;
  readonly evidence_cards: readonly StructuralEvidenceCard[];
}

export interface StructuralHealth {
  readonly assessment_status: string;
  readonly baseline_status: string;
  readonly baseline: {
    readonly id: string;
    readonly code: string;
    readonly revision: string;
    readonly valid_until: string;
  } | null;
  readonly analyses: StructuralPageData<{
    readonly id: string;
    readonly status: string;
    readonly error_code: string | null;
  }>;
  readonly prestress: StructuralPageData<{
    readonly id: string;
    readonly tendon_id: string;
    readonly sensor_id: string;
    readonly value_kn: number;
    readonly observed_at: string;
    readonly source_kind: string;
  }>;
}

export interface StructuralOrder {
  readonly work_order: {
    readonly id: string;
    readonly status: string;
    readonly mission_id: string;
    readonly title: string;
  };
  readonly context: StructuralContext;
  readonly tasks: readonly {
    readonly id: string;
    readonly sequence: number;
    readonly status: string;
    readonly title: string;
    readonly measurement_schema: Readonly<Record<string, unknown>>;
  }[];
  readonly health_reviews: readonly {
    readonly id: string;
    readonly action: string;
    readonly reason: string;
    readonly reviewed_by: string;
    readonly created_at: string;
    readonly assessment: Readonly<Record<string, unknown>>;
  }[];
  readonly retest_handoffs: readonly {
    readonly id: string;
    readonly health_review_id: string;
    readonly modal_id: string | null;
    readonly prestress_id: string | null;
    readonly artifact_uri: string;
    readonly artifact_sha256: string;
    readonly measurement: Readonly<Record<string, unknown>>;
    readonly verified_by: string;
    readonly verified_at: string;
  }[];
}

export interface StructuralCase {
  readonly case: {
    readonly id: string;
    readonly title: string;
    readonly resolution: Readonly<Record<string, unknown>>;
  };
  readonly review: {
    readonly status: string;
    readonly revision: number;
    readonly reviewed_by: string | null;
    readonly review_reason: string | null;
  };
}

export function structuralStatus(value: string): string {
  return (
    (
      {
        no_data: "尚无结构数据",
        analysis_in_progress: "结构分析排队 / 计算中",
        requires_engineering_review: "待工程复核",
        insufficient_data: "数据不足",
        analysis_failed: "分析失败",
        unavailable: "无健康基线",
        expired: "已过期",
        available_for_screening: "基线可用于筛查",
        pending: "待审核",
        approved: "已审核",
        rejected: "已拒绝",
        withdrawn: "已撤回",
        source_changed: "来源已变化",
        awaiting_health_review: "待健康复核",
        completed: "已完成",
        under_review: "待人工审核",
        executing: "执行中",
        failed: "失败",
        succeeded: "分析成功",
        running: "计算中",
        requires_followup: "需追加复测",
        resolve_review: "复核闭环",
      } as Readonly<Record<string, string>>
    )[value] ?? value
  );
}

export function structuralFact(value: unknown): string {
  if (value === null || value === undefined) return "未提供";
  if (Array.isArray(value)) return value.length ? value.map(structuralFact).join("、") : "无";
  if (typeof value === "object")
    return Object.entries(value)
      .map(([key, item]) => `${key}: ${structuralFact(item)}`)
      .join("；");
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean" || typeof value === "bigint")
    return value.toString();
  return "不可展示的值";
}
