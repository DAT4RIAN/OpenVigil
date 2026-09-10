"use client";

import {
  TriangleAlert as AlarmTriangle,
  Check,
  FileSearch,
  MessageSquareText,
  TerminalSquare,
} from "lucide-react";
import { useState } from "react";

import { StatusBadge } from "@/components/data-display/status-badge";
import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/layout/page-header";
import {
  downloadMissionJson,
  MissionActivityTimeline,
  type LocalComment,
} from "@/components/pages/mission-detail-support";
import { Avatar, Button, Card, CardHeader, KeyValue, Progress } from "@/components/ui/primitives";
import { agentDisplayName } from "@/lib/agent-control-meta";
import { agents } from "@/lib/agent-data";
import { getTurbine } from "@/lib/farm-data";
import { activityEvents, decisions, evidenceItems, workOrders } from "@/lib/operations-data";
import type { Mission } from "@/lib/types";
import {
  localizedMissionTitle,
  localizedSeverityLabel,
  localizedStatusLabel,
} from "@/lib/ui-localization";
import { cn } from "@/lib/utils";

import { formatMissionTime, missionProgressSteps } from "./mission-detail-shared";

export function GenericMissionDetailPage({ mission }: { mission: Mission }) {
  const [isCommenting, setIsCommenting] = useState(false);
  const [localComments, setLocalComments] = useState<LocalComment[]>([]);
  const turbine = getTurbine(mission.turbineId);
  const lead = agents.find((item) => item.id === mission.leadAgentId);
  const team = agents.filter((item) => mission.agentIds.includes(item.id));
  const relatedEvidence = evidenceItems.filter((item) => mission.evidenceIds.includes(item.id));
  const events = activityEvents.filter((item) => item.missionId === mission.id);
  const decision = decisions.find((item) => item.id === mission.decisionId);
  const workOrder = workOrders.find((item) => item.id === mission.workOrderId);
  const activeIndex = {
    detected: 0,
    investigating: 1,
    diagnosed: 2,
    "decision-pending": 3,
    "under-review": 4,
    approved: 5,
    executing: 6,
    rejected: 7,
    completed: 7,
  }[mission.status];

  function exportMissionLog() {
    downloadMissionJson(`${mission.id}-mission-log.json`, {
      schemaVersion: "windops.mission-log.v1",
      mission,
      turbine: turbine ?? null,
      leadAgent: lead ?? null,
      participatingAgents: team,
      evidence: relatedEvidence,
      decision: decision ?? null,
      workOrder: workOrder ?? null,
      activity: events,
      sessionComments: {
        persistence: "page-session-only",
        items: localComments,
      },
    });
  }

  return (
    <AppShell runtimeMode="demo" activePath={`/missions/${mission.id}`}>
      <PageHeader
        eyebrow="MISSION 详情"
        title={mission.id}
        description={`${mission.turbineId} · ${localizedMissionTitle(mission.title)} · 结构化协作与执行记录`}
        breadcrumb={["AI 运营", { label: "Mission 中心", href: "/missions" }, mission.id]}
        meta={
          <>
            <StatusBadge
              value={mission.status}
              label={localizedStatusLabel(mission.status)}
              tone={
                mission.status === "completed"
                  ? "success"
                  : mission.status === "under-review"
                    ? "warning"
                    : "info"
              }
              pulse={!(["completed", "approved"] as string[]).includes(mission.status)}
            />
            <StatusBadge
              value={mission.severity}
              label={localizedSeverityLabel(mission.severity)}
              tone={
                mission.severity === "critical"
                  ? "critical"
                  : mission.severity === "high"
                    ? "warning"
                    : "info"
              }
            />
            <span className="page-meta-text">更新于 {formatMissionTime(mission.updatedAt)}</span>
          </>
        }
        actions={
          <>
            <a
              className="button button--secondary button--md"
              href={`/turbines/${mission.turbineId}`}
            >
              <TerminalSquare size={15} /> 查看资产
            </a>
            <Button variant="secondary" onClick={exportMissionLog}>
              <TerminalSquare size={15} /> 导出 JSON
            </Button>
            <Button
              variant="primary"
              onClick={() => setIsCommenting((current) => !current)}
              aria-expanded={isCommenting}
            >
              <MessageSquareText size={15} /> 添加评论
            </Button>
          </>
        }
      />
      <section className="mission-stage-bar" tabIndex={0} aria-label="Mission 阶段，可横向滚动">
        {missionProgressSteps.map((step, index) => (
          <div
            className={cn(
              "mission-stage",
              (index < activeIndex || mission.status === "completed") && "mission-stage--complete",
              index === activeIndex && "mission-stage--active",
            )}
            key={step}
          >
            <span>
              {index < activeIndex || mission.status === "completed" ? (
                <Check size={11} />
              ) : (
                index + 1
              )}
            </span>
            <strong>{step}</strong>
            {index < missionProgressSteps.length - 1 ? <i /> : null}
          </div>
        ))}
        <div className="mission-stage-progress">
          <strong>{mission.progressPercent}%</strong>
          <Progress
            value={mission.progressPercent}
            tone={mission.status === "completed" ? "success" : "info"}
          />
        </div>
      </section>
      <section className="mission-detail-grid">
        <div className="mission-context-column">
          <Card className="mission-overview-card">
            <CardHeader eyebrow="MISSION 概览" title={localizedMissionTitle(mission.title)} />
            <div className="mission-overview-hero">
              <span className="mission-overview-icon">
                <AlarmTriangle size={20} />
              </span>
              <div>
                <span className="mono">
                  {mission.turbineId} · {mission.severity.toUpperCase()}
                </span>
                <p>{mission.summary}</p>
              </div>
            </div>
            <div className="mission-overview-facts">
              <KeyValue
                label="主导 Agent"
                value={lead ? agentDisplayName(lead.id, lead.shortName) : "未指派"}
              />
              <KeyValue label="参与 Agent" value={`${team.length} 个`} />
              <KeyValue label="证据" value={`${relatedEvidence.length} 项`} />
              <KeyValue
                label="目标解决时间"
                value={new Date(mission.targetResolutionAt).toLocaleString("zh-CN")}
              />
            </div>
            <div className="mission-next-action">
              <small>下一步行动</small>
              <strong>{mission.nextAction}</strong>
            </div>
          </Card>
          <Card className="mission-agent-list">
            <CardHeader eyebrow="MISSION 团队" title={`${team.length} 个参与 Agent`} />
            <div>
              {team.map((agent) => (
                <a href={`/agents?agent=${encodeURIComponent(agent.id)}`} key={agent.id}>
                  <Avatar
                    label={agentDisplayName(agent.id, agent.shortName)}
                    tone={
                      agent.layer === "decision"
                        ? "teal"
                        : agent.layer === "review"
                          ? "amber"
                          : "blue"
                    }
                    size="sm"
                  />
                  <span>
                    <strong>{agentDisplayName(agent.id, agent.shortName)}</strong>
                    <small>{agent.role}</small>
                  </span>
                  <StatusBadge value={agent.status} compact />
                </a>
              ))}
            </div>
          </Card>
        </div>
        <MissionActivityTimeline
          events={events}
          agents={agents}
          description="公开结构化摘要，不展示隐藏推理"
          isCommenting={isCommenting}
          onCommentingChange={setIsCommenting}
          localComments={localComments}
          onCommentsChange={setLocalComments}
        />
        <div className="decision-column">
          <Card className="current-decision-card">
            <CardHeader
              eyebrow="当前诊断"
              title={mission.diagnosis ?? "等待诊断"}
              description={
                mission.confidencePercent
                  ? `综合置信度 ${mission.confidencePercent}%`
                  : "证据收集中"
              }
            />
            <div className="decision-recommendation">
              <p>{mission.summary}</p>
              <div className="decision-evidence-summary">
                <span>
                  <FileSearch size={15} />
                </span>
                <div>
                  <strong>{relatedEvidence.length} 项结构化证据</strong>
                  <small>
                    {relatedEvidence
                      .map((item) => item.type.replaceAll("-", " "))
                      .slice(0, 3)
                      .join(" · ") || "等待 Agent 采集"}
                  </small>
                </div>
              </div>
            </div>
          </Card>
          <Card className="weather-resource-card">
            <CardHeader eyebrow="关联对象" title="业务关联" />
            <div className="key-value-list">
              <KeyValue label="风机" value={turbine?.id ?? mission.turbineId} mono />
              <KeyValue label="决策" value={decision?.id ?? "—"} mono />
              <KeyValue label="工单" value={workOrder?.id ?? "—"} mono />
              <KeyValue label="审计事件" value={String(events.length)} />
            </div>
          </Card>
        </div>
      </section>
    </AppShell>
  );
}
