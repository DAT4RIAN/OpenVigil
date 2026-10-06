"use client";

import { useEffect, useRef, useState } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { useOpenVigilIdentity } from "@/components/providers/identity-provider";
import { Button } from "@/components/ui/primitives";
import { apiGet } from "@/lib/api-client";
import {
  structuralFact,
  type StructuralHealth,
  type StructuralOrder,
} from "@/lib/structural-workflow";
import { useStructuralArtifactCommand } from "./structural-artifact-command";
import { FIELD_ARTIFACT_ACCEPT, fieldContentType } from "./work-order-support";
import styles from "./structural-page.module.css";

interface RetestResult {
  readonly evidence: { readonly id: string };
  readonly mission_revision: number;
  readonly work_order_status: string;
}
function isRetestResult(value: unknown): value is RetestResult {
  if (!value || typeof value !== "object") return false;
  const row = value as Partial<RetestResult>;
  return (
    typeof row.evidence?.id === "string" &&
    Number.isInteger(row.mission_revision) &&
    row.work_order_status === "awaiting_health_review"
  );
}

export function StructuralRetestForm({
  order,
  turbineId,
  onLockChange,
}: {
  readonly order: StructuralOrder;
  readonly turbineId: string;
  readonly onLockChange: (locked: boolean) => void;
}) {
  const { session } = useOpenVigilIdentity();
  const client = useQueryClient();
  const command = useStructuralArtifactCommand();
  const [runId, setRunId] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [reference, setReference] = useState("");
  const [result, setResult] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [inputError, setInputError] = useState<string | null>(null);
  const force = order.context.scenario === "prestress_retest";
  const lastReview = order.health_reviews.at(-1);
  const lastTask = [...order.tasks].sort((a, b) => a.sequence - b.sequence).at(-1);
  const permitted = session?.roles.some((role) =>
    ["operations_manager", "field_technician"].includes(role),
  );
  const eligible =
    order.work_order.status === "awaiting_health_review" &&
    lastReview?.action === "requires_followup" &&
    lastTask?.status === "completed";
  const sources = useInfiniteQuery({
    queryKey: ["structural-retest-sources", turbineId, force],
    initialPageParam: null as string | null,
    enabled: eligible && Boolean(permitted),
    queryFn: ({ signal, pageParam }) =>
      apiGet<StructuralHealth>(
        `/api/backend/turbines/${encodeURIComponent(turbineId)}/structural-health?limit=100${pageParam ? `&${force ? "prestress_cursor" : "run_cursor"}=${encodeURIComponent(pageParam)}` : ""}`,
        signal,
      ),
    getNextPageParam: (page) =>
      (force ? page.prestress.next_cursor : page.analyses.next_cursor) ?? undefined,
    retry: false,
  });
  const modes = useQuery({
    queryKey: ["structural-run", runId],
    enabled: eligible && !force && Boolean(runId),
    queryFn: ({ signal }) =>
      apiGet<{
        readonly modal_observations: readonly {
          readonly id: string;
          readonly frequency_hz: number;
        }[];
      }>(`/api/backend/structural-analyses/${encodeURIComponent(runId)}`, signal),
    retry: false,
  });
  const used = new Set(
    (order.retest_handoffs ?? []).map((item) => item.prestress_id ?? item.modal_id),
  );
  const original = new Set(order.context.evidence_cards.map((item) => item.reference.source_id));
  const observations =
    sources.data?.pages
      .flatMap((page) => page.prestress.items)
      .filter(
        (item) =>
          !used.has(item.id) &&
          !original.has(item.id) &&
          Date.parse(item.observed_at) > Date.parse(lastReview?.created_at ?? ""),
      ) ?? [];
  const runs =
    sources.data?.pages
      .flatMap((page) => page.analyses.items)
      .filter((item) => item.status === "succeeded") ?? [];
  useEffect(() => {
    onLockChange(command.busy || command.unknown);
    return () => onLockChange(false);
  }, [command.busy, command.unknown, onLockChange]);

  async function submit() {
    if (!eligible || !permitted || !file) return;
    const contentType = fieldContentType(file);
    if (!contentType) {
      setInputError("请选择 JSON、PDF、JPEG、PNG、TXT 或 MP4 证据文件。");
      return;
    }
    setInputError(null);
    const path = `/api/backend/structural-work-orders/${encodeURIComponent(order.work_order.id)}/retests`;
    const submitted = await command.run(
      {
        file,
        presignPath: `${path}/uploads/presign`,
        presignBody: { content_type: contentType },
        commandPath: path,
        commandBody: {
          expected_mission_revision: order.context.revision,
          result: result.trim(),
          measurement: { retest_source_id: sourceId, measurement_reference: reference.trim() },
        },
      },
      isRetestResult,
      "追加复测已保存，等待独立健康复核。",
    );
    if (submitted) {
      setSourceId("");
      setRunId("");
      setFile(null);
      setReference("");
      setResult("");
      if (fileInput.current) fileInput.current.value = "";
      await Promise.all([
        client.invalidateQueries({ queryKey: ["structural-order", order.work_order.id] }),
        client.invalidateQueries({ queryKey: ["structural-context", order.work_order.mission_id] }),
        client.invalidateQueries({ queryKey: ["production-mission-detail"] }),
        client.invalidateQueries({ queryKey: ["work-orders"] }),
      ]);
    }
  }

  if (!eligible) return null;
  return (
    <section className={styles.item} aria-label="追加复测提交">
      <h3>提交新采集的复测证据</h3>
      <p>
        先在采集区登记新测量。此处追加证据，保留首次现场任务及全部复核历史；服务端重新核验采集时间、构件、方法、校准和适用域。
      </p>
      <p>
        关联复核 {lastReview?.id} · Mission 修订 {order.context.revision}
      </p>
      {!permitted ? (
        <p>当前角色可查看历史，提交需要现场技术员或运维经理。</p>
      ) : (
        <>
          {sources.isPending ? <p role="status">正在读取已登记观测…</p> : null}
          {sources.error ? (
            <p role="alert">
              {sources.error.message}
              <Button onClick={() => void sources.refetch()}>重试观测</Button>
            </p>
          ) : null}
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void submit();
            }}
          >
            <fieldset disabled={command.busy || command.unknown} className={styles.formFields}>
              {!force ? (
                <label className={styles.field}>
                  复测分析记录
                  <select
                    required
                    value={runId}
                    onChange={(event) => {
                      setRunId(event.target.value);
                      setSourceId("");
                    }}
                  >
                    <option value="">请选择成功分析</option>
                    {runs.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.id}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <label className={styles.field}>
                {force ? "新采集索力观测" : "新采集模态观测"}
                <select
                  required
                  value={sourceId}
                  onChange={(event) => setSourceId(event.target.value)}
                >
                  <option value="">请选择新观测</option>
                  {force
                    ? observations.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.value_kn} kN · {item.observed_at} · {item.source_kind}
                        </option>
                      ))
                    : modes.data?.modal_observations
                        .filter((item) => !used.has(item.id) && !original.has(item.id))
                        .map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.frequency_hz} Hz · {item.id}
                          </option>
                        ))}
                </select>
              </label>
              {modes.error ? (
                <p role="alert">
                  {modes.error.message}
                  <Button onClick={() => void modes.refetch()}>重试分析详情</Button>
                </p>
              ) : null}
              <label className={styles.field}>
                追加测量记录引用
                <input
                  required
                  minLength={3}
                  maxLength={320}
                  value={reference}
                  onChange={(event) => setReference(event.target.value)}
                />
              </label>
              <label className={styles.field}>
                追加现场结论
                <textarea
                  required
                  minLength={3}
                  maxLength={4000}
                  value={result}
                  onChange={(event) => setResult(event.target.value)}
                />
              </label>
              <label className={styles.field}>
                追加复测证据文件
                <input
                  required
                  type="file"
                  ref={fileInput}
                  accept={FIELD_ARTIFACT_ACCEPT}
                  onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                />
              </label>
            </fieldset>
            {command.unknown ? (
              <p role="status">提交结果待核验。表单保持冻结，重试将使用原测量、修订和幂等键。</p>
            ) : null}
            <div className={styles.row}>
              <Button
                loading={command.busy}
                disabled={
                  !file ||
                  (!command.unknown &&
                    (!sourceId || reference.trim().length < 3 || result.trim().length < 3))
                }
                type="submit"
              >
                {command.unknown ? "核验原复测提交" : "上传并提交追加复测"}
              </Button>
              <Button
                disabled={command.busy || command.unknown}
                onClick={() => void sources.refetch()}
              >
                刷新新观测
              </Button>
              {sources.hasNextPage ? (
                <Button
                  loading={sources.isFetchingNextPage}
                  disabled={command.busy || command.unknown}
                  onClick={() => void sources.fetchNextPage()}
                >
                  更多复测观测
                </Button>
              ) : null}
            </div>
          </form>
        </>
      )}
      {inputError || command.error ? (
        <p role="alert" className={styles.error}>
          {inputError ?? command.error}
        </p>
      ) : null}
      {command.notice ? <p role="status">{command.notice}</p> : null}
      {!sources.isPending && !sources.error && permitted && force && !observations.length ? (
        <p>当前已载入观测中没有在本次复核后新采集的索力测量，请先登记或读取更多观测。</p>
      ) : null}
    </section>
  );
}

export function StructuralRetestHistory({ order }: { readonly order: StructuralOrder }) {
  return (
    <section aria-label="追加复测历史">
      <h3>追加复测历史</h3>
      {(order.retest_handoffs ?? []).length ? (
        order.retest_handoffs.map((item) => (
          <article className={styles.item} key={item.id}>
            <p>
              观测 {item.modal_id ?? item.prestress_id} · 关联复核 {item.health_review_id}
            </p>
            <p>{structuralFact(item.measurement)}</p>
            <p>SHA-256 {item.artifact_sha256}</p>
            <small>
              {item.verified_by} · {item.verified_at}
            </small>
          </article>
        ))
      ) : (
        <p>尚无追加复测，首次现场证据保留在任务记录中。</p>
      )}
    </section>
  );
}
