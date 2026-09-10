export type QueryLifecycleState =
  | "initial-loading"
  | "refreshing"
  | "success-empty"
  | "success-data"
  | "error-stale"
  | "error-no-data";

export type RuntimeHealthStatus = "ready" | "degraded" | "stale" | "offline";

export type QueryErrorKind = "permission" | "conflict" | "network" | "service" | "unknown";

export interface QueryErrorDetails {
  readonly kind: QueryErrorKind;
  readonly status: number | null;
  readonly code: string;
  readonly correlationId: string | null;
  readonly message: string;
}

export interface QueryViewState {
  readonly lifecycle: QueryLifecycleState;
  readonly health: RuntimeHealthStatus;
  readonly hasData: boolean;
  readonly lastSuccessAt: number | null;
  readonly error: QueryErrorDetails | null;
}

export interface RuntimeHealthSnapshot {
  readonly status: RuntimeHealthStatus;
  readonly label: "Ready" | "Degraded" | "Stale" | "Offline";
  readonly detail: string;
  readonly lastSuccessAt: number | null;
}

interface QueryStateInput<T> {
  readonly data: T | undefined;
  readonly dataUpdatedAt: number;
  readonly error: unknown;
  readonly isError: boolean;
  readonly isFetching: boolean;
  readonly isPending: boolean;
  readonly isStale: boolean;
  readonly isEmpty: (data: T) => boolean;
  readonly sourceUpdatedAt?: number | null;
  readonly staleAfterMs?: number;
  readonly now?: number;
}

const healthLabels: Record<RuntimeHealthStatus, RuntimeHealthSnapshot["label"]> = {
  ready: "Ready",
  degraded: "Degraded",
  stale: "Stale",
  offline: "Offline",
};

function finiteTimestamp(value: number | null | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : null;
}

export function latestValidTimestamp(
  values: readonly (string | null | undefined)[],
): number | null {
  const timestamps = values
    .map((value) => (value ? Date.parse(value) : Number.NaN))
    .filter(Number.isFinite);
  return timestamps.length > 0 ? Math.max(...timestamps) : null;
}

export function queryErrorDetails(error: unknown): QueryErrorDetails | null {
  if (error === null || error === undefined) return null;
  const value = error as {
    readonly status?: unknown;
    readonly code?: unknown;
    readonly correlationId?: unknown;
    readonly message?: unknown;
  };
  const status = typeof value.status === "number" ? value.status : null;
  const code = typeof value.code === "string" && value.code ? value.code : "QUERY_FAILED";
  const correlationId =
    typeof value.correlationId === "string" && value.correlationId ? value.correlationId : null;
  const message =
    typeof value.message === "string" && value.message ? value.message : "查询未能完成。";
  const kind: QueryErrorKind =
    status === 401 || status === 403
      ? "permission"
      : status === 409
        ? "conflict"
        : status === 0 || code === "NETWORK_FAILURE"
          ? "network"
          : status !== null && status >= 500
            ? "service"
            : "unknown";
  return { kind, status, code, correlationId, message };
}

export function deriveQueryViewState<T>(input: QueryStateInput<T>): QueryViewState {
  const hasData = input.data !== undefined;
  const error = input.isError ? queryErrorDetails(input.error) : null;
  const sourceUpdatedAt = finiteTimestamp(input.sourceUpdatedAt);
  const dataUpdatedAt = finiteTimestamp(input.dataUpdatedAt);
  const lastSuccessAt = sourceUpdatedAt ?? dataUpdatedAt;
  const sourceIsStale =
    sourceUpdatedAt !== null &&
    (input.now ?? Date.now()) - sourceUpdatedAt > (input.staleAfterMs ?? 60_000);

  let lifecycle: QueryLifecycleState;
  if (!hasData && (input.isPending || !input.isError)) lifecycle = "initial-loading";
  else if (input.isError) lifecycle = hasData ? "error-stale" : "error-no-data";
  else if (hasData && input.isFetching) lifecycle = "refreshing";
  else if (hasData && input.isEmpty(input.data as T)) lifecycle = "success-empty";
  else lifecycle = "success-data";

  let health: RuntimeHealthStatus;
  if (lifecycle === "error-no-data") {
    health = error?.kind === "permission" || error?.kind === "conflict" ? "degraded" : "offline";
  } else if (lifecycle === "error-stale" || input.isStale || sourceIsStale) {
    health = "stale";
  } else if (lifecycle === "initial-loading") {
    health = "degraded";
  } else {
    health = "ready";
  }

  return { lifecycle, health, hasData, lastSuccessAt, error };
}

export function queryRuntimeHealth(
  state: QueryViewState,
  target: string,
  options: { readonly partial?: boolean } = {},
): RuntimeHealthSnapshot {
  const status =
    options.partial &&
    (state.lifecycle === "initial-loading" || state.lifecycle.startsWith("error-"))
      ? "degraded"
      : state.health;
  const detail =
    state.lifecycle === "initial-loading"
      ? `${target}正在建立权威读取`
      : state.lifecycle === "refreshing"
        ? `${target}正在刷新，保留上次成功数据`
        : state.lifecycle === "error-stale"
          ? `${target}刷新失败，当前显示上次成功数据`
          : state.lifecycle === "error-no-data"
            ? `${target}没有可验证的数据`
            : status === "stale"
              ? `${target}数据已过期`
              : `${target}权威读取已确认`;
  return { status, label: healthLabels[status], detail, lastSuccessAt: state.lastSuccessAt };
}

export function mergeRuntimeHealth(
  ...states: readonly (RuntimeHealthSnapshot | null | undefined)[]
): RuntimeHealthSnapshot {
  const available = states.filter((state): state is RuntimeHealthSnapshot => state != null);
  if (!available.length) {
    return {
      status: "degraded",
      label: "Degraded",
      detail: "当前页面尚未确认依赖状态",
      lastSuccessAt: null,
    };
  }
  const rank: Record<RuntimeHealthStatus, number> = {
    ready: 0,
    degraded: 1,
    stale: 2,
    offline: 3,
  };
  return available.reduce((worst, state) =>
    rank[state.status] > rank[worst.status] ? state : worst,
  );
}

export function runtimeHealthTone(status: RuntimeHealthStatus): "success" | "warning" | "offline" {
  return status === "ready" ? "success" : status === "offline" ? "offline" : "warning";
}
