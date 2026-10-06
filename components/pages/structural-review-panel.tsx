"use client";

import { useEffect, useState } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { useOpenVigilIdentity } from "@/components/providers/identity-provider";
import { Button, Card, CardHeader } from "@/components/ui/primitives";
import { apiGet } from "@/lib/api-client";
import {
  structuralFact,
  structuralStatus,
  type StructuralCase,
  type StructuralClaim,
  type StructuralContext,
  type StructuralOrder,
} from "@/lib/structural-workflow";
import { useStructuralCommand } from "./structural-command";
import { StructuralRetestForm, StructuralRetestHistory } from "./structural-retest-form";
import { StructuralEvidenceCards } from "./structural-evidence-cards";
import styles from "./structural-page.module.css";

export function StructuralReviewPanel({ missionId }: { readonly missionId: string }) {
  const { session, can } = useOpenVigilIdentity();
  const client = useQueryClient();
  const command = useStructuralCommand();
  const [reason, setReason] = useState("");
  const contextQuery = useQuery({
    queryKey: ["structural-context", missionId],
    queryFn: ({ signal }) =>
      apiGet<StructuralContext>(
        `/api/backend/structural-missions/${encodeURIComponent(missionId)}`,
        signal,
      ),
    retry: false,
    refetchInterval: 10000,
  });
  const context = contextQuery.data;
  const claimQuery = useQuery({
    queryKey: ["structural-claim", context?.claim_id],
    enabled: Boolean(context?.claim_id),
    queryFn: ({ signal }) =>
      apiGet<StructuralClaim>(
        `/api/backend/engineering-claims/${encodeURIComponent(context?.claim_id ?? "")}`,
        signal,
      ),
    retry: false,
  });
  const claim = claimQuery.data;
  const reviewRole = session?.roles.some((role) =>
    ["operations_manager", "maintenance_reviewer"].includes(role),
  );
  async function review(action: "approve" | "reject" | "withdraw") {
    if (!claim || !reviewRole || reason.trim().length < 3) return;
    if (
      await command.run(
        `/api/backend/engineering-claims/${claim.id}/review`,
        { expected_revision: claim.revision, action, reason },
        "工程结论审核已保存。",
      )
    )
      await client.invalidateQueries({ queryKey: ["structural-claim"] });
  }
  if (contextQuery.isPending) return <p role="status">正在读取结构 Mission…</p>;
  if (contextQuery.error)
    return (
      <div role="alert" className={styles.notice}>
        {contextQuery.error.message}
        <Button onClick={() => void contextQuery.refetch()}>重试</Button>
      </div>
    );
  return (
    <Card className={styles.panel}>
      <CardHeader
        title="工程结论与独立审核"
        description="审核授权受控复测建议；损伤概率、现场资格与恢复运行权限仍未确认。"
      />
      <p>
        {structuralStatus(context?.status ?? "")} · 修订 {context?.revision}
      </p>
      <dl className={styles.facts}>
        <dt>结构比较</dt>
        <dd>{structuralFact(context?.comparison)}</dd>
        <dt>缺失证据</dt>
        <dd>{structuralFact(context?.missing_evidence)}</dd>
      </dl>
      {claimQuery.isPending && context?.claim_id ? <p role="status">正在读取工程结论…</p> : null}
      {claimQuery.error ? (
        <p role="alert">
          {claimQuery.error.message}
          <Button onClick={() => void claimQuery.refetch()}>重试</Button>
        </p>
      ) : null}
      {claim ? (
        <>
          <h3>
            {structuralStatus(claim.effective_status)} · 工程结论修订 {claim.revision}
          </h3>
          <p>{claim.conclusion}</p>
          <p>
            作者 {claim.created_by} · 有效至 {claim.valid_until}
          </p>
          <StructuralEvidenceCards cards={claim.evidence_cards} />
          <label className={styles.field}>
            工程审核意见
            <textarea
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              maxLength={4000}
            />
          </label>
          <div className={styles.row}>
            {(["approve", "reject", "withdraw"] as const).map((action) => (
              <Button
                key={action}
                loading={command.busy}
                disabled={
                  !reviewRole ||
                  claim.created_by === session?.subject ||
                  reason.trim().length < 3 ||
                  (action === "withdraw"
                    ? claim.effective_status !== "approved"
                    : claim.effective_status !== "pending")
                }
                onClick={() => void review(action)}
              >
                {action === "approve"
                  ? "审核复测建议"
                  : action === "reject"
                    ? "拒绝结论"
                    : "撤回结论"}
              </Button>
            ))}
          </div>
          {claim.reviews.map((item) => (
            <p key={item.id}>
              {item.reviewed_by} · {item.action} · {item.reason}
            </p>
          ))}
        </>
      ) : (
        <p>尚无工程结论，分析完成后可刷新。</p>
      )}
      {command.error ? (
        <p role="alert" className={styles.error}>
          {command.error}
        </p>
      ) : null}
      {command.notice ? <p role="status">{command.notice}</p> : null}
      <div className={styles.row}>
        <a href={`/missions/${encodeURIComponent(missionId)}`}>打开 Mission 审批与执行记录</a>
        <Button
          disabled={!can("view.missions")}
          onClick={() =>
            void client.invalidateQueries({ queryKey: ["structural-context", missionId] })
          }
        >
          刷新
        </Button>
      </div>
    </Card>
  );
}

export function StructuralHealthReview({
  workOrderId,
  turbineId,
  onLockChange,
}: {
  readonly workOrderId: string;
  readonly turbineId: string;
  readonly onLockChange?: (locked: boolean) => void;
}) {
  const { session } = useOpenVigilIdentity();
  const client = useQueryClient();
  const command = useStructuralCommand();
  const [reason, setReason] = useState("");
  const [outcome, setOutcome] = useState("inconclusive");
  const [retestLocked, setRetestLocked] = useState(false);
  useEffect(() => {
    onLockChange?.(retestLocked || command.busy);
    return () => onLockChange?.(false);
  }, [retestLocked, command.busy, onLockChange]);
  const orderQuery = useQuery({
    queryKey: ["structural-order", workOrderId],
    queryFn: ({ signal }) =>
      apiGet<StructuralOrder>(
        `/api/backend/structural-work-orders/${encodeURIComponent(workOrderId)}`,
        signal,
      ),
    retry: false,
  });
  const casesQuery = useInfiniteQuery({
    queryKey: ["structural-cases", turbineId],
    initialPageParam: null as string | null,
    queryFn: ({ signal, pageParam }) =>
      apiGet<{ readonly items: readonly StructuralCase[]; readonly next_cursor: string | null }>(
        `/api/backend/structural-cases?turbine_id=${encodeURIComponent(turbineId)}${pageParam ? `&cursor=${encodeURIComponent(pageParam)}` : ""}`,
        signal,
      ),
    retry: false,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const order = orderQuery.data;
  const reviewRole = session?.roles.some((role) =>
    ["operations_manager", "maintenance_reviewer"].includes(role),
  );
  async function review(action: "resolve_review" | "requires_followup") {
    if (!order || !reviewRole || reason.trim().length < 3) return;
    const result = await command.run(
      `/api/backend/structural-work-orders/${workOrderId}/health-review`,
      {
        expected_mission_revision: order.context.revision,
        action,
        reason,
        hypothesis_outcome: outcome,
      },
      "健康复核已保存。",
    );
    if (result)
      await Promise.all([
        client.invalidateQueries({ queryKey: ["structural-order"] }),
        client.invalidateQueries({ queryKey: ["structural-context"] }),
        client.invalidateQueries({ queryKey: ["structural-cases"] }),
        client.invalidateQueries({ queryKey: ["work-orders"] }),
        client.invalidateQueries({ queryKey: ["production-mission-detail"] }),
      ]);
  }
  async function publish(item: StructuralCase, action: "approve" | "reject") {
    if (!reviewRole || reason.trim().length < 3) return;
    if (
      await command.run(
        `/api/backend/structural-cases/${item.case.id}/review`,
        { expected_revision: item.review.revision, action, reason },
        "案例审核已保存。",
      )
    )
      await client.invalidateQueries({ queryKey: ["structural-cases"] });
  }
  return (
    <Card className={styles.panel}>
      <CardHeader
        title="复测后的健康复核"
        description="所有现场任务完成后，由独立审核人核验实际测量、校准、规程与适用域。"
      />
      {orderQuery.isPending ? <p role="status">正在读取工单…</p> : null}
      {orderQuery.error ? (
        <p role="alert">
          {orderQuery.error.message}
          <Button onClick={() => void orderQuery.refetch()}>重试</Button>
        </p>
      ) : null}
      {order ? (
        <>
          <h3>
            {order.work_order.title} · {structuralStatus(order.work_order.status)}
          </h3>
          {order.tasks.map((task) => (
            <p key={task.id}>
              {task.sequence}. {task.title} · {structuralStatus(task.status)}
            </p>
          ))}
          <a href="/work-orders">打开现场任务与制品上传</a>
          {order.health_reviews.map((item) => (
            <article className={styles.item} key={item.id}>
              <h3>{structuralStatus(item.action)}</h3>
              <p>{item.reason}</p>
              <p>{structuralFact(item.assessment)}</p>
              <small>
                {item.reviewed_by} · {item.created_at}
              </small>
            </article>
          ))}
          <StructuralRetestHistory order={order} />
          <StructuralRetestForm
            key={order.work_order.id}
            order={order}
            turbineId={turbineId}
            onLockChange={setRetestLocked}
          />
          <label className={styles.field}>
            健康复核意见
            <textarea
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              maxLength={4000}
            />
          </label>
          <label className={styles.field}>
            异常假设复核结果
            <select value={outcome} onChange={(event) => setOutcome(event.target.value)}>
              <option value="inconclusive">证据不足</option>
              <option value="supported">支持异常假设</option>
              <option value="not_supported">不支持异常假设</option>
            </select>
          </label>
          <div className={styles.row}>
            {(["resolve_review", "requires_followup"] as const).map((action) => (
              <Button
                key={action}
                loading={command.busy}
                disabled={
                  !reviewRole ||
                  retestLocked ||
                  order.work_order.status !== "awaiting_health_review" ||
                  reason.trim().length < 3
                }
                onClick={() => void review(action)}
              >
                {action === "resolve_review" ? "保存复核并关单" : "保留告警，追加复测"}
              </Button>
            ))}
          </div>
        </>
      ) : null}
      <h3>待审结构案例</h3>
      {casesQuery.isPending ? <p role="status">正在读取案例…</p> : null}
      {casesQuery.error ? (
        <p role="alert">
          {casesQuery.error.message}
          <Button onClick={() => void casesQuery.refetch()}>重试</Button>
        </p>
      ) : null}
      {casesQuery.data?.pages
        .flatMap((page) => page.items)
        .map((item) => (
          <article className={styles.item} key={item.case.id}>
            <h3>{item.case.title}</h3>
            <p>{structuralFact(item.case.resolution.hypothesis_outcome)}</p>
            <p>
              {structuralStatus(item.review.status)} · 修订 {item.review.revision}
            </p>
            <Button
              disabled={
                !reviewRole ||
                item.case.resolution.responsible_reviewer === session?.subject ||
                reason.trim().length < 3
              }
              loading={command.busy}
              onClick={() => void publish(item, "approve")}
            >
              审核进入检索
            </Button>
            <Button
              disabled={!reviewRole || reason.trim().length < 3}
              loading={command.busy}
              onClick={() => void publish(item, "reject")}
            >
              拒绝案例
            </Button>
          </article>
        ))}
      {casesQuery.data && !casesQuery.data.pages.some((page) => page.items.length) ? (
        <p>尚无待审案例。</p>
      ) : null}
      {casesQuery.hasNextPage ? (
        <Button
          loading={casesQuery.isFetchingNextPage}
          onClick={() => void casesQuery.fetchNextPage()}
        >
          更多待审案例
        </Button>
      ) : null}
      {command.error ? (
        <p role="alert" className={styles.error}>
          {command.error}
        </p>
      ) : null}
      {command.notice ? <p role="status">{command.notice}</p> : null}
      <Button onClick={() => void orderQuery.refetch()}>刷新复核状态</Button>
    </Card>
  );
}
