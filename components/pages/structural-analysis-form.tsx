"use client";

import { useEffect, useState } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/primitives";
import { apiGet } from "@/lib/api-client";
import { isStructuralObject, optionalNumber } from "@/lib/structural-acquisition";
import { structuralFact, structuralStatus } from "@/lib/structural-workflow";
import { useStructuralCommand } from "./structural-command";
import styles from "./structural-page.module.css";

interface AnalysisDetail {
  readonly id: string;
  readonly status: string;
  readonly error_code: string | null;
  readonly attempts: number;
  readonly result: { readonly quality?: unknown; readonly warnings?: readonly string[] } | null;
  readonly modal_observations: readonly {
    readonly id: string;
    readonly frequency_hz: number;
    readonly quality: unknown;
  }[];
}

export function StructuralAnalysisForm({
  turbineId,
  recordId,
  onRecordChange,
  onLockChange,
}: {
  readonly turbineId: string;
  readonly recordId: string;
  readonly onRecordChange: (id: string) => void;
  readonly onLockChange: (locked: boolean) => void;
}) {
  const client = useQueryClient();
  const command = useStructuralCommand();
  const [runId, setRunId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [config, setConfig] = useState({
    nperseg: "1024",
    min_frequency_hz: "0.05",
    max_frequency_hz: "3",
    max_modes: "4",
  });
  useEffect(() => {
    onLockChange(command.busy || command.unknown);
    return () => onLockChange(false);
  }, [command.busy, command.unknown, onLockChange]);
  const records = useInfiniteQuery({
    queryKey: ["structural-records", turbineId],
    initialPageParam: null as string | null,
    queryFn: ({ signal, pageParam }) =>
      apiGet<{
        readonly items: readonly {
          readonly id: string;
          readonly started_at: string;
          readonly source_kind: string;
        }[];
        readonly next_cursor: string | null;
      }>(
        `/api/backend/structural-records?turbine_id=${encodeURIComponent(turbineId)}&limit=50${pageParam ? `&cursor=${encodeURIComponent(pageParam)}` : ""}`,
        signal,
      ),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    retry: false,
  });
  const detail = useQuery({
    queryKey: ["structural-run", runId],
    enabled: Boolean(runId),
    queryFn: ({ signal }) =>
      apiGet<AnalysisDetail>(
        `/api/backend/structural-analyses/${encodeURIComponent(runId)}`,
        signal,
      ),
    retry: false,
    refetchInterval: (query) =>
      ["pending", "running"].includes(query.state.data?.status ?? "") ? 5000 : false,
  });
  const status = detail.data?.status;
  useEffect(() => {
    if (status && !["pending", "running"].includes(status))
      void client.invalidateQueries({ queryKey: ["structural-health", turbineId] });
  }, [status, client, turbineId]);
  const items = records.data?.pages.flatMap((page) => page.items) ?? [];
  async function submit() {
    if (!recordId) return;
    setError(null);
    try {
      const saved = await command.run(
        "/api/backend/structural-analyses",
        {
          record_id: recordId,
          method: "pyoma2_fdd_v1",
          config: Object.fromEntries(
            Object.entries(config).map(([key, value]) => [key, optionalNumber(value, key)]),
          ),
        },
        "分析已入队，结果以后台运行状态为准。",
        isStructuralObject,
      );
      if (saved) setRunId(saved.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "请检查分析参数。");
    }
  }
  return (
    <section aria-label="结构分析提交">
      <h3>独立后台模态分析</h3>
      <p>
        FDD 频率候选用于复核；未量化损伤概率、绝对索力和阻尼。参数须与后续健康基线的方法版本一致。
      </p>
      {records.error ? (
        <p role="alert">
          {records.error.message}
          <Button onClick={() => void records.refetch()}>重试记录</Button>
        </p>
      ) : null}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <fieldset className={styles.formFields} disabled={command.busy || command.unknown}>
          <label className={styles.field}>
            已登记波形记录
            <select
              required
              value={recordId}
              onChange={(event) => {
                onRecordChange(event.target.value);
                setRunId("");
              }}
            >
              <option value="">请选择实际记录</option>
              {recordId && !items.some((item) => item.id === recordId) ? (
                <option value={recordId}>新登记记录 · {recordId}</option>
              ) : null}
              {items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.started_at} · {item.source_kind} · {item.id}
                </option>
              ))}
            </select>
          </label>
          {(["nperseg", "min_frequency_hz", "max_frequency_hz", "max_modes"] as const).map(
            (key, index) => (
              <label className={styles.field} key={key}>
                {["谱窗点数", "最低频率 (Hz)", "最高频率 (Hz)", "最多模态数"][index]}
                <input
                  required
                  type="number"
                  min={[64, 0.000001, 0.000001, 1][index]}
                  max={key === "nperseg" ? 8192 : key === "max_modes" ? 8 : undefined}
                  step={key === "nperseg" || key === "max_modes" ? "1" : "any"}
                  value={config[key]}
                  onChange={(event) => setConfig({ ...config, [key]: event.target.value })}
                />
              </label>
            ),
          )}
        </fieldset>
        <div className={styles.row}>
          <Button type="submit" loading={command.busy} disabled={!recordId}>
            {command.unknown ? "核验原分析提交" : "提交后台分析"}
          </Button>
          {records.hasNextPage ? (
            <Button
              loading={records.isFetchingNextPage}
              disabled={command.busy || command.unknown}
              onClick={() => void records.fetchNextPage()}
            >
              更多波形记录
            </Button>
          ) : null}
        </div>
      </form>
      {error || command.error ? (
        <p role="alert" className={styles.error}>
          {error ?? command.error}
        </p>
      ) : null}
      {command.notice ? <p role="status">{command.notice}</p> : null}
      {runId && detail.isPending ? <p role="status">正在读取分析状态…</p> : null}
      {detail.error ? (
        <p role="alert">
          {detail.error.message}
          <Button onClick={() => void detail.refetch()}>重试分析状态</Button>
        </p>
      ) : null}
      {detail.data ? (
        <div className={styles.item} aria-label="实际分析结果">
          <h3>
            {detail.data.status === "pending" ? "排队中" : structuralStatus(detail.data.status)} ·{" "}
            {detail.data.id}
          </h3>
          <p>
            计算尝试 {detail.data.attempts} · {detail.data.error_code ?? "无错误代码"}
          </p>
          <p>质量 {structuralFact(detail.data.result?.quality)}</p>
          <p>{structuralFact(detail.data.result?.warnings)}</p>
          {detail.data.modal_observations.map((item) => (
            <p key={item.id}>
              {item.frequency_hz} Hz · 观测 {item.id} · {structuralFact(item.quality)}
            </p>
          ))}
          <Button onClick={() => void detail.refetch()}>刷新计算状态</Button>
        </div>
      ) : null}
    </section>
  );
}
