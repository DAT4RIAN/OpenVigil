"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  LoaderCircle,
  RefreshCcw,
  ShieldAlert,
  WifiOff,
} from "lucide-react";
import type { QueryViewState, RuntimeHealthSnapshot } from "@/lib/query-state";
import { runtimeHealthTone } from "@/lib/query-state";
import { StatusBadge } from "@/components/data-display/status-badge";
import { Button } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

function formatTimestamp(timestamp: number | null): string {
  if (timestamp === null) return "本次会话尚无成功响应";
  return `上次成功 ${new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "Asia/Shanghai",
  }).format(timestamp)} CST`;
}

export function RuntimeHealthBadge({
  health,
  compact = false,
}: {
  readonly health: RuntimeHealthSnapshot;
  readonly compact?: boolean;
}) {
  return (
    <span title={`${health.detail}；${formatTimestamp(health.lastSuccessAt)}`}>
      <StatusBadge
        value={health.status}
        label={health.label}
        tone={runtimeHealthTone(health.status)}
        pulse={health.status === "ready"}
        compact={compact}
      />
    </span>
  );
}

export interface PartialQueryFailure {
  readonly module: string;
  readonly code: string;
  readonly detail: string;
  readonly lastSuccessAt: number | null;
}

export type OperationLifecycle = "idle" | "running" | "success" | "failed" | "result-unknown";

export interface OperationViewState {
  readonly lifecycle: OperationLifecycle;
  readonly startedAt?: number;
  readonly completedAt?: number;
  readonly operationKey?: string | null;
  readonly code?: string | null;
  readonly message?: string | null;
}

export function OperationStateNotice({
  state,
  target,
  onRetry,
  onReconcile,
}: {
  readonly state: OperationViewState;
  readonly target: string;
  readonly onRetry?: () => void;
  readonly onReconcile?: () => void;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (state.lifecycle !== "running") return;
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, [state.lifecycle]);
  if (state.lifecycle === "idle") return null;

  const running = state.lifecycle === "running";
  const unknown = state.lifecycle === "result-unknown";
  const failed = state.lifecycle === "failed";
  const success = state.lifecycle === "success";
  const elapsedSeconds = state.startedAt
    ? Math.max(0, Math.floor(((state.completedAt ?? now) - state.startedAt) / 1_000))
    : 0;
  const title = running
    ? `${target}正在运行`
    : unknown
      ? `${target}结果尚未确认`
      : failed
        ? `${target}未完成`
        : `${target}已完成`;
  const description = running
    ? `已运行 ${elapsedSeconds} 秒；请求受幂等键保护。当前同步接口不提供独立心跳或取消能力，网关会在受控时限内返回最终结果。`
    : unknown
      ? "两次传输均未收到权威响应，后端可能已经提交。不要创建新命令；请使用同一幂等键核验结果。"
      : failed
        ? (state.message ?? "权威服务明确拒绝或终止了本次命令，可以修正后安全重试。")
        : (state.message ?? "权威服务已确认完成，最新读取结果已刷新。");

  return (
    <section
      className={cn(
        "query-state query-state--operation",
        running && "query-state--loading",
        unknown && "query-state--stale",
        failed && "query-state--error",
        success && "query-state--success",
      )}
      role={running || success ? "status" : "alert"}
      aria-live={running || success ? "polite" : "assertive"}
      aria-busy={running ? "true" : undefined}
    >
      <span className="query-state__icon" aria-hidden="true">
        {running ? (
          <LoaderCircle className="query-state__spin" size={19} />
        ) : unknown ? (
          <WifiOff size={19} />
        ) : success ? (
          <CheckCircle2 size={19} />
        ) : (
          <AlertTriangle size={19} />
        )}
      </span>
      <span className="query-state__copy">
        <strong>{title}</strong>
        <span>{description}</span>
        {state.operationKey || state.code ? (
          <small className="mono">
            {state.code ?? "IDEMPOTENT_COMMAND"}
            {state.operationKey ? ` · 幂等键：${state.operationKey}` : ""}
          </small>
        ) : null}
      </span>
      {unknown && onReconcile ? (
        <Button variant="secondary" onClick={onReconcile}>
          <RefreshCcw size={14} /> 使用同一键核验
        </Button>
      ) : failed && onRetry ? (
        <Button variant="secondary" onClick={onRetry}>
          <RefreshCcw size={14} /> 重试
        </Button>
      ) : null}
    </section>
  );
}

export function PartialFailureNotice({
  target,
  failures,
  onRetry,
}: {
  readonly target: string;
  readonly failures: readonly PartialQueryFailure[];
  readonly onRetry?: () => void;
}) {
  if (failures.length === 0) return null;
  return (
    <section
      className="query-state query-state--stale query-state--partial"
      role="alert"
      aria-live="polite"
    >
      <span className="query-state__icon" aria-hidden="true">
        <AlertTriangle size={19} />
      </span>
      <span className="query-state__copy">
        <strong>{target}部分数据不可用</strong>
        <span>成功模块继续显示；以下模块保留各自的数据时间，不以零值代替未知结果。</span>
        <span className="query-state__failures">
          {failures.map((failure) => (
            <span key={`${failure.module}-${failure.code}`}>
              <strong>{failure.module}</strong>
              <small>
                {failure.detail} · {failure.code} · {formatTimestamp(failure.lastSuccessAt)}
              </small>
            </span>
          ))}
        </span>
      </span>
      {onRetry ? (
        <Button variant="secondary" onClick={onRetry}>
          <RefreshCcw size={14} /> 重试失败模块
        </Button>
      ) : null}
    </section>
  );
}

export function QueryStateNotice({
  state,
  target,
  impact,
  onRetry,
  partial = false,
  className,
}: {
  readonly state: QueryViewState;
  readonly target: string;
  readonly impact: string;
  readonly onRetry?: () => void;
  readonly partial?: boolean;
  readonly className?: string;
}) {
  if (state.lifecycle === "success-data" || state.lifecycle === "success-empty") {
    if (state.health !== "stale") return null;
  }

  const loading = state.lifecycle === "initial-loading";
  const refreshing = state.lifecycle === "refreshing";
  const stale = state.lifecycle === "error-stale" || state.health === "stale";
  const permission = state.error?.kind === "permission";
  const conflict = state.error?.kind === "conflict";
  const offline = state.error?.kind === "network" || state.health === "offline";
  const title = loading
    ? `正在加载${target}`
    : refreshing
      ? `正在刷新${target}`
      : permission
        ? `没有权限读取${target}`
        : conflict
          ? `${target}已发生状态冲突`
          : stale
            ? `${target}不是最新状态`
            : `${target}当前不可用`;
  const description = loading
    ? `正在读取权威服务；${impact}在响应完成前不会显示为零值或空状态。`
    : refreshing
      ? `${formatTimestamp(state.lastSuccessAt)}；现有内容暂时保留，依赖最新 revision 的操作不可用。`
      : permission
        ? `${formatTimestamp(state.lastSuccessAt)}；当前身份或数据范围无权读取此内容。${impact}未被加载，也不会泄露受限对象。`
        : conflict
          ? `${formatTimestamp(state.lastSuccessAt)}；服务器状态已变化，请刷新权威数据后重新复核。${impact}不会自动覆盖。`
          : stale
            ? `${formatTimestamp(state.lastSuccessAt)}；刷新失败或数据已过期，${impact}不能作为实时结论。`
            : `${formatTimestamp(state.lastSuccessAt)}；${impact}已失败关闭；不会回退到 Demo、fixture 或伪造空数据。`;
  const Icon = loading
    ? LoaderCircle
    : refreshing
      ? RefreshCcw
      : permission
        ? ShieldAlert
        : offline
          ? WifiOff
          : AlertTriangle;
  const role = loading || refreshing ? "status" : "alert";

  return (
    <section
      className={cn(
        "query-state",
        `query-state--${loading || refreshing ? "loading" : stale ? "stale" : "error"}`,
        partial && "query-state--partial",
        className,
      )}
      role={role}
      aria-live={role === "alert" ? "assertive" : "polite"}
      aria-busy={loading || refreshing ? "true" : undefined}
    >
      <span className="query-state__icon" aria-hidden="true">
        <Icon className={loading || refreshing ? "query-state__spin" : undefined} size={19} />
      </span>
      <span className="query-state__copy">
        <strong>{title}</strong>
        <span>{description}</span>
        {!loading && !refreshing ? (
          <small className="mono">
            {state.error?.code ?? "DATA_STALE"} · 关联 ID：
            {state.error?.correlationId ?? "无服务器响应"}
          </small>
        ) : null}
      </span>
      {onRetry && !loading ? (
        <Button variant="secondary" onClick={onRetry}>
          <RefreshCcw size={14} /> {conflict ? "刷新权威状态" : "重试"}
        </Button>
      ) : null}
      {loading && !partial ? (
        <span className="query-state__skeleton" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
      ) : null}
    </section>
  );
}
