"use client";

import { useState } from "react";
import {
  Activity,
  TriangleAlert as AlarmTriangle,
  Bot,
  FileSearch,
  GitBranch,
  Link2,
  MessageSquareText,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
  UserCheck,
  Wrench,
} from "lucide-react";
import { StatusBadge } from "@/components/data-display/status-badge";
import { Avatar, Button, Card, CardHeader } from "@/components/ui/primitives";
import type { DemoWorkflowEvent } from "@/lib/demo-workflow";
import type { ActivityEvent, Agent, MissionStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

type ActivityFilter = "all" | "agents" | "evidence" | "reviews";

export type LocalComment = {
  id: string;
  text: string;
  timestamp: string;
};

const activityFilters: { label: string; value: ActivityFilter }[] = [
  { label: "All activity", value: "all" },
  { label: "Agents", value: "agents" },
  { label: "Evidence", value: "evidence" },
  { label: "Reviews", value: "reviews" },
];

const activityIcon: Record<ActivityEvent["kind"], typeof Activity> = {
  detection: AlarmTriangle,
  analysis: Activity,
  retrieval: FileSearch,
  diagnosis: Sparkles,
  decision: GitBranch,
  review: ShieldCheck,
  approval: UserCheck,
  "work-order": Wrench,
  execution: TerminalSquare,
  system: Bot,
};

function formatTime(timestamp: string) {
  return new Date(timestamp).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function matchesActivityFilter(event: ActivityEvent, filter: ActivityFilter) {
  if (filter === "agents") return Boolean(event.agentId);
  if (filter === "evidence") return event.evidenceIds.length > 0;
  if (filter === "reviews") return event.kind === "review" || event.kind === "approval";
  return true;
}

export function downloadMissionJson(filename: string, payload: unknown) {
  const blob = new Blob([`${JSON.stringify(payload, null, 2)}\n`], {
    type: "application/json;charset=utf-8",
  });
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(href);
}

export function MissionActivityTimeline({
  events,
  agents,
  auditTrail = [],
  missionStatus,
  description,
  isCommenting,
  onCommentingChange,
  localComments,
  onCommentsChange,
}: {
  events: readonly ActivityEvent[];
  agents: readonly Agent[];
  auditTrail?: readonly DemoWorkflowEvent[];
  missionStatus?: MissionStatus;
  description: string;
  isCommenting: boolean;
  onCommentingChange: (open: boolean) => void;
  localComments: readonly LocalComment[];
  onCommentsChange: (comments: LocalComment[]) => void;
}) {
  const [activityFilter, setActivityFilter] = useState<ActivityFilter>("all");
  const [commentDraft, setCommentDraft] = useState("");
  const filteredEvents = events.filter((event) => matchesActivityFilter(event, activityFilter));
  const showAuditTrail = activityFilter === "all" || activityFilter === "reviews";
  const showLocalComments = activityFilter === "all";
  const hasVisibleActivity =
    filteredEvents.length > 0 ||
    (showAuditTrail && auditTrail.length > 0) ||
    (showLocalComments && localComments.length > 0);

  function addLocalComment() {
    const text = commentDraft.trim();
    if (!text) return;
    onCommentsChange([
      ...localComments,
      {
        id: `local-comment-${localComments.length + 1}`,
        text,
        timestamp: new Date().toISOString(),
      },
    ]);
    setCommentDraft("");
    onCommentingChange(false);
    setActivityFilter("all");
  }

  return (
    <Card className="mission-timeline-card">
      <CardHeader
        eyebrow={missionStatus ? "LIVE ACTIVITY" : "ACTIVITY TRACE"}
        title="Agent Activity Timeline"
        description={description}
        action={
          missionStatus ? (
            <StatusBadge
              value={missionStatus}
              label="AUDITED"
              tone="info"
              pulse={missionStatus !== "completed"}
              compact
            />
          ) : undefined
        }
      />
      <div className="timeline-filter" aria-label="活动类型筛选">
        {activityFilters.map((filter) => (
          <button
            className={activityFilter === filter.value ? "active" : undefined}
            key={filter.value}
            type="button"
            aria-pressed={activityFilter === filter.value}
            onClick={() => setActivityFilter(filter.value)}
          >
            {filter.label}
          </button>
        ))}
      </div>
      {isCommenting ? (
        <div className="approval-gate" id="mission-comment-composer">
          <textarea
            className="approval-comment"
            aria-label="添加临时评论"
            placeholder="输入本次页面会话的评论"
            value={commentDraft}
            onChange={(event) => setCommentDraft(event.target.value)}
          />
          <small>仅本次页面会话可见，不写入审计记录，也不会持久化。</small>
          <div className="approval-actions">
            <Button variant="secondary" onClick={() => onCommentingChange(false)}>
              Cancel
            </Button>
            <Button variant="primary" disabled={!commentDraft.trim()} onClick={addLocalComment}>
              Add local comment
            </Button>
          </div>
        </div>
      ) : null}
      <div className="mission-timeline">
        {filteredEvents.map((event, index) => {
          const Icon = activityIcon[event.kind];
          const agent = event.agentId ? agents.find((item) => item.id === event.agentId) : null;
          const isCurrent =
            index === filteredEvents.length - 1 &&
            (!showAuditTrail || auditTrail.length === 0) &&
            (!showLocalComments || localComments.length === 0);
          return (
            <div
              className={cn("timeline-event", isCurrent && "timeline-event--current")}
              key={event.id}
            >
              <time>{formatTime(event.timestamp)}</time>
              <span className={`timeline-event__node timeline-event__node--${event.outcome}`}>
                <Icon size={13} />
              </span>
              <div className="timeline-event__body">
                <div>
                  <span>
                    <Avatar
                      label={agent?.shortName ?? event.actorLabel}
                      tone={event.kind === "review" ? "amber" : "teal"}
                      size="sm"
                    />
                    <span>
                      <strong>{agent?.shortName ?? event.actorLabel}</strong>
                      <small>{event.kind}</small>
                    </span>
                  </span>
                  <StatusBadge
                    value={event.outcome}
                    label={event.outcome.toUpperCase()}
                    tone={
                      event.outcome === "success"
                        ? "success"
                        : event.outcome === "attention"
                          ? "warning"
                          : event.outcome === "in-progress"
                            ? "info"
                            : "neutral"
                    }
                    compact
                  />
                </div>
                <h3>{event.title}</h3>
                <p>{event.detail}</p>
                {event.evidenceIds.length ? (
                  <div className="timeline-evidence">
                    <Link2 size={11} /> {event.evidenceIds.length} linked evidence
                  </div>
                ) : null}
              </div>
            </div>
          );
        })}
        {showAuditTrail
          ? auditTrail.map((event, index) => (
              <div
                className={cn(
                  "timeline-event",
                  index === auditTrail.length - 1 &&
                    (!showLocalComments || localComments.length === 0) &&
                    "timeline-event--current",
                )}
                key={event.id}
              >
                <time>{formatTime(event.timestamp)}</time>
                <span className="timeline-event__node timeline-event__node--success">
                  <UserCheck size={13} />
                </span>
                <div className="timeline-event__body">
                  <div>
                    <span>
                      <Avatar label={event.actor} tone="amber" size="sm" />
                      <span>
                        <strong>{event.actor}</strong>
                        <small>{event.kind}</small>
                      </span>
                    </span>
                    <StatusBadge value="audited" label="AUDITED" tone="success" compact />
                  </div>
                  <h3>{event.title}</h3>
                  <p>{event.detail}</p>
                  <div className="timeline-evidence">
                    <Link2 size={11} /> immutable demo audit
                  </div>
                </div>
              </div>
            ))
          : null}
        {showLocalComments
          ? localComments.map((localComment, index) => (
              <div
                className={cn(
                  "timeline-event",
                  index === localComments.length - 1 && "timeline-event--current",
                )}
                key={localComment.id}
              >
                <time>{formatTime(localComment.timestamp)}</time>
                <span className="timeline-event__node timeline-event__node--in-progress">
                  <MessageSquareText size={13} />
                </span>
                <div className="timeline-event__body">
                  <div>
                    <span>
                      <Avatar label="当前用户" tone="amber" size="sm" />
                      <span>
                        <strong>当前用户</strong>
                        <small>comment</small>
                      </span>
                    </span>
                    <StatusBadge value="local" label="LOCAL ONLY" tone="warning" compact />
                  </div>
                  <h3>临时评论</h3>
                  <p>{localComment.text}</p>
                  <div className="timeline-evidence">
                    <MessageSquareText size={11} /> 仅本次页面会话，不写入审计记录
                  </div>
                </div>
              </div>
            ))
          : null}
        {!hasVisibleActivity ? <div className="command-empty">当前筛选下没有活动记录</div> : null}
      </div>
    </Card>
  );
}
