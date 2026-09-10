"use client";

import { Bot, MessageSquareText, TerminalSquare } from "lucide-react";
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { StatusBadge } from "@/components/data-display/status-badge";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import { useOpenVigilIdentity } from "@/components/providers/identity-provider";
import { Button, Card, CardHeader, KeyValue } from "@/components/ui/primitives";
import { apiGet, apiPostCommand, createIdempotencyKey } from "@/lib/api-client";

interface ProductionMissionComment {
  readonly comment_id: string;
  readonly body: string;
  readonly author_subject: string;
  readonly author_email: string | null;
  readonly created_at: string;
}

interface ProductionMissionDetail {
  readonly mission_id: string;
  readonly alarm_id: string;
  readonly turbine_id: string;
  readonly title: string;
  readonly status: string;
  readonly revision: number;
  readonly public_state: Readonly<Record<string, unknown>>;
  readonly work_order_id: string | null;
  readonly evidence: readonly {
    readonly evidence_id: string;
    readonly evidence_type: string;
    readonly summary: string;
    readonly citation_uri: string | null;
    readonly created_at: string;
  }[];
  readonly decision: {
    readonly decision_id: string;
    readonly status: string;
    readonly recommendation_reason: string;
    readonly recommended_alternative_id: string;
    readonly selected_alternative_id: string | null;
    readonly alternatives: readonly {
      readonly alternative_id: string;
      readonly title?: string;
    }[];
  } | null;
  readonly approvals: readonly {
    readonly approval_id: string;
    readonly action: string;
    readonly approver: string;
    readonly reason: string;
    readonly comment: string;
    readonly created_at: string;
  }[];
  readonly executions: readonly {
    readonly execution_id: string;
    readonly node: string;
    readonly agent_role: string;
    readonly status: string;
    readonly latency_ms: number;
    readonly provider: string;
    readonly model: string;
    readonly started_at: string;
  }[];
  readonly created_at: string;
  readonly updated_at: string;
}

interface ProductionMissionCommentsResponse {
  readonly comments: readonly ProductionMissionComment[];
}

async function persistMissionComment(
  missionId: string,
  body: string,
): Promise<ProductionMissionComment> {
  return apiPostCommand<ProductionMissionComment>(
    `/api/backend/missions/${encodeURIComponent(missionId)}/comments`,
    { body },
    createIdempotencyKey("mission-comment"),
  );
}

export function ProductionMissionDetailPage({ missionId }: { readonly missionId: string }) {
  const { can } = useOpenVigilIdentity();
  const canComment = can("mission.comment");
  const [isCommenting, setIsCommenting] = useState(false);
  const [commentDraft, setCommentDraft] = useState("");
  const [approvalReason, setApprovalReason] = useState("");
  const [approvalComment, setApprovalComment] = useState("");
  const [approvalMessage, setApprovalMessage] = useState<string | null>(null);
  const approvalInFlight = useRef(false);
  const queryClient = useQueryClient();
  const detailQuery = useQuery({
    queryKey: ["production-mission-detail", missionId],
    queryFn: ({ signal }) =>
      apiGet<ProductionMissionDetail>(
        `/api/backend/missions/${encodeURIComponent(missionId)}`,
        signal,
      ),
  });
  const commentsQuery = useQuery({
    queryKey: ["production-mission-comments", missionId],
    queryFn: ({ signal }) =>
      apiGet<ProductionMissionCommentsResponse>(
        `/api/backend/missions/${encodeURIComponent(missionId)}/comments`,
        signal,
      ),
  });
  const commentMutation = useMutation({
    mutationFn: (body: string) => {
      if (!canComment) throw new Error("当前角色没有写入 Mission 评论的权限。");
      return persistMissionComment(missionId, body);
    },
    onSuccess: async () => {
      setCommentDraft("");
      setIsCommenting(false);
      await queryClient.invalidateQueries({
        queryKey: ["production-mission-comments", missionId],
      });
    },
  });
  const mission = detailQuery.data;
  const approvalMutation = useMutation({
    mutationFn: (action: "approve" | "reject" | "request_revision" | "escalate") => {
      if (!mission) throw new Error("Mission 尚未加载完成。");
      const capability =
        action === "approve"
          ? "mission.approve"
          : action === "reject"
            ? "mission.reject"
            : action === "request_revision"
              ? "mission.request_revision"
              : "mission.escalate";
      if (!can(capability)) throw new Error("当前角色没有执行此审批动作的权限。");
      return apiPostCommand<{
        readonly mission_status: string;
        readonly work_order_id: string | null;
      }>(
        `/api/backend/missions/${encodeURIComponent(missionId)}/approvals`,
        {
          action,
          expected_revision: mission.revision,
          selected_alternative_id:
            action === "approve" ? mission.decision?.recommended_alternative_id : null,
          reason: approvalReason.trim(),
          comment: approvalComment.trim(),
        },
        createIdempotencyKey(`mission-${action}`),
      );
    },
    onSuccess: async (result) => {
      setApprovalReason("");
      setApprovalComment("");
      setApprovalMessage(
        result.work_order_id
          ? `审批已记录并创建工单 ${result.work_order_id}。`
          : `审批已记录，Mission 状态为 ${result.mission_status}。`,
      );
      await queryClient.invalidateQueries({ queryKey: ["production-mission-detail", missionId] });
    },
    onSettled: () => {
      approvalInFlight.current = false;
    },
  });
  const submitProductionApproval = (
    action: "approve" | "reject" | "request_revision" | "escalate",
  ) => {
    if (approvalInFlight.current) return;
    approvalInFlight.current = true;
    approvalMutation.mutate(action);
  };

  if (!mission) {
    return (
      <AppShell runtimeMode="production" activePath={`/missions/${missionId}`}>
        <PageHeader
          eyebrow="MISSION 详情"
          title={missionId}
          description="从权威 Mission、证据、决策、审批和 Agent 执行账本加载。"
          breadcrumb={["AI 运营", { label: "Mission 中心", href: "/missions" }, missionId]}
        />
        <Card>
          <CardHeader
            eyebrow={detailQuery.isError ? "加载失败" : "加载中"}
            title={detailQuery.isError ? "Mission 不可用" : "正在读取权威记录"}
            description={
              detailQuery.error instanceof Error
                ? detailQuery.error.message
                : "生产模式不会回退到演示 Mission。"
            }
          />
          {detailQuery.isError ? (
            <Button onClick={() => void detailQuery.refetch()}>重试</Button>
          ) : null}
        </Card>
      </AppShell>
    );
  }

  const diagnosis = mission.public_state.diagnosis;
  const diagnosisText =
    typeof diagnosis === "object" && diagnosis !== null
      ? JSON.stringify(diagnosis, null, 2)
      : "尚未形成结构化诊断。";

  return (
    <AppShell runtimeMode="production" activePath={`/missions/${mission.mission_id}`}>
      <PageHeader
        eyebrow="MISSION 详情"
        title={mission.mission_id}
        description={`${mission.turbine_id} · ${mission.title} · 权威协作与执行记录`}
        breadcrumb={["AI 运营", { label: "Mission 中心", href: "/missions" }, mission.mission_id]}
        meta={
          <>
            <StatusBadge value={mission.status} label={mission.status} tone="info" />
            <span className="page-meta-text">修订 {mission.revision}</span>
            <span className="page-meta-text">
              更新于 {new Date(mission.updated_at).toLocaleString("zh-CN")}
            </span>
          </>
        }
        actions={
          <>
            <a
              className="button button--secondary button--md"
              href={`/turbines/${mission.turbine_id}`}
            >
              <TerminalSquare size={15} /> 查看资产
            </a>
            <Button
              variant="primary"
              onClick={() => setIsCommenting((current) => !current)}
              aria-expanded={isCommenting}
              disabled={!canComment}
              title={canComment ? undefined : "当前角色没有 mission.comment capability"}
            >
              <MessageSquareText size={15} /> 添加评论
            </Button>
          </>
        }
      />

      <section className="mission-detail-grid">
        <div className="mission-context-column">
          <Card className="mission-overview-card">
            <CardHeader eyebrow="权威状态" title={mission.title} />
            <div className="mission-overview-facts">
              <KeyValue label="告警" value={mission.alarm_id} />
              <KeyValue label="资产" value={mission.turbine_id} />
              <KeyValue label="证据" value={`${mission.evidence.length} 项`} />
              <KeyValue label="工单" value={mission.work_order_id ?? "尚未创建"} />
            </div>
          </Card>
          <Card>
            <CardHeader eyebrow="结构化诊断" title="公开诊断输出" />
            <pre className="mono">{diagnosisText}</pre>
          </Card>
          <Card>
            <CardHeader eyebrow="证据链" title={`${mission.evidence.length} 项可追溯证据`} />
            <div className="mission-evidence-list">
              {mission.evidence.map((item) => (
                <div key={item.evidence_id}>
                  <strong>{item.summary}</strong>
                  <small>
                    {item.evidence_id} · {item.evidence_type}
                  </small>
                  {item.citation_uri ? <code>{item.citation_uri}</code> : null}
                </div>
              ))}
              {!mission.evidence.length ? <p>尚无持久化证据。</p> : null}
            </div>
          </Card>
        </div>

        <Card className="mission-timeline-card">
          <CardHeader
            eyebrow="持久化协作"
            title="评论与 Agent 执行"
            description="评论写入 PostgreSQL 并进入领域事件审计，不再局限于当前页面会话。"
          />
          {isCommenting && canComment ? (
            <div className="approval-gate" id="mission-comment-composer">
              <textarea
                className="approval-comment"
                aria-label="添加持久化评论"
                placeholder="输入需要保留在 Mission 审计记录中的评论"
                value={commentDraft}
                onChange={(event) => setCommentDraft(event.target.value)}
              />
              <small>评论将使用当前委派身份写入不可变活动记录。</small>
              {commentMutation.error instanceof Error ? (
                <p role="alert">{commentMutation.error.message}</p>
              ) : null}
              <div className="approval-actions">
                <Button variant="secondary" onClick={() => setIsCommenting(false)}>
                  取消
                </Button>
                <Button
                  variant="primary"
                  loading={commentMutation.isPending}
                  disabled={!commentDraft.trim()}
                  onClick={() => commentMutation.mutate(commentDraft.trim())}
                >
                  写入评论
                </Button>
              </div>
            </div>
          ) : null}
          <div
            className="mission-timeline"
            role="region"
            tabIndex={0}
            aria-label="评论与 Agent 执行，可滚动"
          >
            {mission.executions.map((execution) => (
              <div className="timeline-event" key={execution.execution_id}>
                <time>{new Date(execution.started_at).toLocaleString("zh-CN")}</time>
                <span className="timeline-event__node timeline-event__node--success">
                  <Bot size={13} />
                </span>
                <div className="timeline-event__body">
                  <h3>{execution.node}</h3>
                  <p>
                    {execution.agent_role} · {execution.provider}/{execution.model} ·{" "}
                    {execution.latency_ms} ms
                  </p>
                  <StatusBadge value={execution.status} label={execution.status} compact />
                </div>
              </div>
            ))}
            {(commentsQuery.data?.comments ?? []).map((comment) => (
              <div className="timeline-event" key={comment.comment_id}>
                <time>{new Date(comment.created_at).toLocaleString("zh-CN")}</time>
                <span className="timeline-event__node timeline-event__node--in-progress">
                  <MessageSquareText size={13} />
                </span>
                <div className="timeline-event__body">
                  <h3>{comment.author_email ?? comment.author_subject}</h3>
                  <p>{comment.body}</p>
                  <StatusBadge value="persisted" label="已持久化" tone="success" compact />
                </div>
              </div>
            ))}
          </div>
        </Card>

        <div className="decision-column">
          <Card>
            <CardHeader eyebrow="当前决策" title={mission.decision?.decision_id ?? "尚未形成"} />
            {mission.decision ? (
              <>
                <StatusBadge
                  value={mission.decision.status}
                  label={mission.decision.status}
                  tone="warning"
                />
                <p>{mission.decision.recommendation_reason}</p>
                <KeyValue label="推荐方案" value={mission.decision.recommended_alternative_id} />
                <KeyValue
                  label="已选方案"
                  value={mission.decision.selected_alternative_id ?? "等待人工审批"}
                />
              </>
            ) : (
              <p>Agent 分析仍在进行，尚无持久化决策。</p>
            )}
          </Card>
          <Card>
            <CardHeader eyebrow="人工门禁" title={`${mission.approvals.length} 条审批记录`} />
            {mission.status === "under_review" &&
            (can("mission.approve") ||
              can("mission.reject") ||
              can("mission.request_revision") ||
              can("mission.escalate")) ? (
              <div className="approval-gate" data-capability="mission.approval">
                <label>
                  <span>审批原因</span>
                  <input
                    value={approvalReason}
                    onChange={(event) => setApprovalReason(event.target.value)}
                    placeholder="关联风险审查或变更依据"
                  />
                </label>
                <label>
                  <span>补充意见</span>
                  <textarea
                    className="approval-comment"
                    value={approvalComment}
                    onChange={(event) => setApprovalComment(event.target.value)}
                  />
                </label>
                <div className="approval-actions">
                  {can("mission.request_revision") ? (
                    <Button
                      variant="secondary"
                      disabled={approvalMutation.isPending || approvalReason.trim().length < 3}
                      onClick={() => submitProductionApproval("request_revision")}
                    >
                      要求修订
                    </Button>
                  ) : null}
                  {can("mission.escalate") ? (
                    <Button
                      variant="secondary"
                      disabled={approvalMutation.isPending || approvalReason.trim().length < 3}
                      onClick={() => submitProductionApproval("escalate")}
                    >
                      升级处理
                    </Button>
                  ) : null}
                  {can("mission.reject") ? (
                    <Button
                      variant="secondary"
                      disabled={approvalMutation.isPending || approvalReason.trim().length < 3}
                      onClick={() => submitProductionApproval("reject")}
                    >
                      驳回
                    </Button>
                  ) : null}
                  {can("mission.approve") ? (
                    <Button
                      variant="primary"
                      loading={approvalMutation.isPending}
                      disabled={approvalMutation.isPending || approvalReason.trim().length < 3}
                      onClick={() => submitProductionApproval("approve")}
                    >
                      批准推荐方案
                    </Button>
                  ) : null}
                </div>
                {approvalMutation.error instanceof Error ? (
                  <p role="alert">{approvalMutation.error.message}</p>
                ) : null}
                {approvalMessage ? <p role="status">{approvalMessage}</p> : null}
              </div>
            ) : null}
            {mission.status === "under_review" &&
            !can("mission.approve") &&
            !can("mission.reject") &&
            !can("mission.request_revision") &&
            !can("mission.escalate") ? (
              <p role="status">当前角色可审阅此 Mission，但没有可执行的审批动作。</p>
            ) : null}
            {mission.approvals.map((approval) => (
              <div key={approval.approval_id}>
                <strong>{approval.action}</strong>
                <p>{approval.reason}</p>
                <small>
                  {approval.approver} · {new Date(approval.created_at).toLocaleString("zh-CN")}
                </small>
              </div>
            ))}
            {!mission.approvals.length ? <p>等待具备权限的人员审批。</p> : null}
          </Card>
        </div>
      </section>
    </AppShell>
  );
}
