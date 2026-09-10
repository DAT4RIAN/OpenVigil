import type { ModelRegistryEntry } from "@/lib/platform-admin-data";

export type ModelEnvelope = {
  data: readonly ModelRegistryEntry[];
  meta: {
    count: number;
    total: number;
    deterministic: boolean;
    readOnly: boolean;
    snapshotAt: string;
    realInferenceCount: number;
    embeddingBackedCount: number;
    artifactCount?: number;
    activeDeploymentCount?: number;
    monitoring?: {
      predictionCount: number;
      succeededCount: number;
      failedCount: number;
      successRate: number | null;
      p95LatencyMs: number;
      lastPredictionAt: string | null;
    };
    disclosure: string;
  };
};

export type ModelUploadGrant = {
  model_id: string;
  artifact_uri: string;
  upload_url: string;
  required_headers: Record<string, string>;
};

export type BenchmarkMetric = {
  readonly name: string;
  readonly value: number;
  readonly unit: string;
  readonly is_release_metric: boolean;
  readonly threshold_value: number | null;
  readonly threshold_direction: string | null;
  readonly passed: boolean | null;
};

export type BenchmarkEvaluation = {
  readonly evaluation_run_id: string;
  readonly model: {
    readonly model_id: string;
    readonly version: string;
    readonly kind: string;
    readonly algorithm: string | null;
    readonly evaluation_role: string | null;
    readonly artifact: { readonly present: boolean; readonly sha256: string | null };
  };
  readonly run: {
    readonly kind: string;
    readonly status: string;
    readonly farm: string | null;
    readonly protocol_version: string;
    readonly feature_set_version: string;
    readonly quality_rule_version: string;
    readonly threshold_policy_version: string;
    readonly threshold_policy_sha256: string;
    readonly random_seed: number;
    readonly input_identity_sha256: string;
    readonly prediction_truth_used: boolean | null;
    readonly dependency_identity: Readonly<Record<string, string>> | null;
    readonly invalidated_at: string | null;
  };
  readonly event_accounting: {
    readonly requested: number;
    readonly scored: number;
    readonly failed: number;
    readonly unscorable: number;
  };
  readonly evaluation_artifact: {
    readonly uri: string | null;
    readonly sha256: string | null;
    readonly present: boolean;
    readonly immutable: boolean;
  };
  readonly metrics: readonly BenchmarkMetric[];
  readonly metrics_truncated: boolean;
  readonly server_gate: {
    readonly eligible: boolean;
    readonly reasons: readonly string[];
    readonly release_metric_count: number;
  };
  readonly deployments: readonly {
    readonly deployment_id: string;
    readonly status: string;
    readonly target_id: string;
    readonly authorization_state: "current" | "stale" | "inactive" | "not-authorized-for-run";
  }[];
};

export type BenchmarkEvaluationEnvelope = {
  readonly data: readonly BenchmarkEvaluation[];
  readonly meta: {
    readonly count: number;
    readonly filtered_total: number;
    readonly bounds: {
      readonly evaluation_page_max: number;
      readonly metrics_per_evaluation_max: number;
    };
  };
};

export type BenchmarkEventResultEnvelope = {
  readonly data: readonly {
    readonly result_id: string;
    readonly event_id: number;
    readonly farm: string;
    readonly status: "scored" | "failed" | "unscorable";
    readonly scorable: boolean;
    readonly anomaly_detected: boolean | null;
    readonly scores: {
      readonly care: number | null;
      readonly coverage: number | null;
      readonly accuracy: number | null;
      readonly reliability: number | null;
      readonly earliness: number | null;
    };
    readonly failure_code: string | null;
    readonly result_sha256: string;
    readonly prediction_artifact: { readonly present: boolean; readonly sha256: string | null };
    readonly truth: {
      readonly access: "restricted" | "revealed";
      readonly event_label: string | null;
      readonly failure_type: string | null;
      readonly description: string | null;
    };
  }[];
  readonly meta: {
    readonly count: number;
    readonly filtered_total: number;
    readonly truth_revealed: boolean;
    readonly truth_reveal_allowed: boolean;
    readonly bounds: { readonly event_result_page_max: number };
  };
};
