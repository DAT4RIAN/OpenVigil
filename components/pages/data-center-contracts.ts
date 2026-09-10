import { assetCatalogHierarchy, type DataCatalogEntry } from "@/lib/platform-admin-data";

export type CatalogEnvelope = {
  data: readonly DataCatalogEntry[];
  meta: {
    count: number;
    total: number;
    deterministic: boolean;
    readOnly: boolean;
    snapshotAt: string | null;
    hierarchy: typeof assetCatalogHierarchy;
    schemaObjects: readonly string[];
    schemaObjectCount: number;
    scadaArchiveCount: number;
  };
};

export type PlatformDataGovernanceEnvelope = {
  data_sources: readonly {
    source_id: string;
    display_name: string;
    source_kind: string;
    enabled: boolean;
    policy: Readonly<Record<string, unknown>>;
    secret_configured: boolean;
    updated_at: string;
  }[];
  data_contracts: readonly {
    contract_id: string;
    source_id: string;
    variable: string;
    revision: number;
    contract: Readonly<Record<string, unknown>>;
  }[];
};

export type BenchmarkDataset = {
  readonly dataset_version_id: string;
  readonly dataset_id: string;
  readonly version: string;
  readonly status: string;
  readonly manifest: { readonly uri: string; readonly sha256: string };
  readonly archive: {
    readonly size_bytes: number;
    readonly file_count: number;
    readonly content_sha256: string;
    readonly md5: string | null;
    readonly sha256: string | null;
  };
  readonly license: {
    readonly name: string;
    readonly url: string;
    readonly doi: string;
    readonly citation: string;
    readonly attribution: Readonly<Record<string, unknown>>;
  };
  readonly coverage: {
    readonly registered_file_count: number;
    readonly registered_event_count: number;
    readonly farm_count: number;
    readonly asset_count: number;
    readonly train_row_count: number;
    readonly prediction_row_count: number;
    readonly time_point_count: number;
    readonly truth_summary: {
      readonly access: "restricted" | "revealed";
      readonly anomaly_event_count: number | null;
      readonly normal_event_count: number | null;
    };
  };
  readonly layers: Readonly<
    Record<
      string,
      { readonly status: string; readonly event_count?: number; readonly file_count?: number }
    >
  >;
  readonly mapping: {
    readonly total: number;
    readonly enabled: number;
    readonly disabled: number;
    readonly unknown_unit: number;
    readonly failed: number;
  };
  readonly quality: {
    readonly report_count: number;
    readonly completed_count: number;
    readonly failed_count: number;
    readonly mask_count: number;
    readonly raw_values_modified: boolean;
    readonly quality_rule_versions: readonly string[];
    readonly feature_set_versions: readonly string[];
  };
  readonly runs: {
    readonly import: { readonly status: string };
    readonly evaluation: Readonly<Record<string, number>>;
    readonly replay: Readonly<Record<string, number>>;
  };
  readonly created_at: string;
};

export type BenchmarkDatasetEnvelope = {
  readonly data: readonly BenchmarkDataset[];
  readonly meta: {
    readonly count: number;
    readonly total: number;
    readonly filtered_total: number;
    readonly offset: number;
    readonly limit: number;
    readonly has_more: boolean;
    readonly next_offset: number | null;
    readonly bounds: Readonly<Record<string, number>>;
  };
};

export type BenchmarkReplaySummary = {
  readonly replay_run_id: string;
  readonly status: string;
  readonly online_turbine_id: string;
  readonly replay_anchor_at: string;
  readonly variables: readonly string[];
  readonly variable_count: number;
  readonly variables_truncated: boolean;
};

export type BenchmarkEvent = {
  readonly benchmark_event_id: string;
  readonly event_id: number;
  readonly farm: "A" | "B" | "C";
  readonly source_asset_id: string;
  readonly logical_asset_id: string;
  readonly rows: {
    readonly train: number;
    readonly prediction: number;
    readonly total: number;
  };
  readonly truth: {
    readonly access: "restricted" | "revealed";
    readonly event_label: string | null;
  };
  readonly quality: {
    readonly status: string;
    readonly quality_rule_version: string | null;
    readonly feature_set_version: string | null;
    readonly mask_count: number;
    readonly raw_values_modified: boolean;
  };
  readonly evaluation_results: Readonly<Record<string, number>>;
  readonly recent_replays: readonly BenchmarkReplaySummary[];
};

export type BenchmarkEventEnvelope = {
  readonly data: readonly BenchmarkEvent[];
  readonly meta: {
    readonly count: number;
    readonly filtered_total: number;
    readonly offset: number;
    readonly limit: number;
    readonly has_more: boolean;
    readonly next_offset: number | null;
    readonly truth_revealed: boolean;
  };
};

export type BenchmarkCurveEnvelope = {
  readonly data: readonly {
    readonly observed_at: string;
    readonly value: number;
    readonly unit: string;
    readonly quality: string;
    readonly source_row_id: number | null;
    readonly observed_at_is_synthetic: boolean;
  }[];
  readonly meta: {
    readonly replay_run_id: string;
    readonly variable: string;
    readonly count: number;
    readonly source_point_count: number;
    readonly max_points: number;
    readonly downsample_algorithm: string;
    readonly bounded: boolean;
    readonly raw_csv_loaded: boolean;
    readonly truth_included: boolean;
    readonly time_semantics: string;
  };
};
