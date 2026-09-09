import type { ServerWorkflowSnapshot } from "./server-workflow-contract";
import type { ActivityEvent, Alarm } from "./types";

/** Select an alarm frame after applying the authoritative workflow completion overlay. */
export function selectRealtimeAlarm(
  items: readonly Alarm[],
  sequence: number,
  workflow?: ServerWorkflowSnapshot,
): Alarm {
  const source = workflow
    ? items.map((alarm) =>
        workflow.workOrder.status === "completed" && alarm.missionId === workflow.mission.id
          ? {
              ...alarm,
              status: "resolved" as const,
              aiStatus: "action-created" as const,
              acknowledgedAt: alarm.acknowledgedAt ?? workflow.updatedAt,
              resolvedAt: workflow.updatedAt,
            }
          : alarm,
      )
    : items;
  return source[sequence % source.length]!;
}

/** Public alarm WebSocket payload, including every mutable alarm field. */
export function realtimeAlarmData(alarm: Alarm): Readonly<Record<string, unknown>> {
  return Object.freeze({
    id: alarm.id,
    turbineId: alarm.turbineId,
    severity: alarm.severity,
    status: alarm.status,
    assignee: alarm.assignee,
    acknowledgedAt: alarm.acknowledgedAt,
    resolvedAt: alarm.resolvedAt,
    title: alarm.title,
    missionId: alarm.missionId,
    currentValue: alarm.currentValue,
    threshold: alarm.threshold,
    unit: alarm.unit,
  });
}

/** Derive public Agent activity from the same workflow audit snapshot used by REST. */
export function realtimeAgentActivityData(
  activity: ActivityEvent,
  sequence: number,
  workflow?: ServerWorkflowSnapshot,
): Readonly<Record<string, unknown>> {
  const workflowEvent = workflow?.auditEvents.length
    ? workflow.auditEvents[sequence % workflow.auditEvents.length]
    : null;
  return Object.freeze({
    id: workflowEvent?.id ?? activity.id,
    missionId: workflowEvent?.missionId ?? activity.missionId,
    agentId: workflowEvent?.actor.id ?? activity.agentId,
    actorLabel: workflowEvent?.actor.name ?? activity.actorLabel,
    kind: workflowEvent?.kind ?? activity.kind,
    title: workflowEvent ? `WT-023 ${workflowEvent.action}` : activity.title,
    detail: workflowEvent?.detail ?? activity.detail,
    outcome:
      workflowEvent?.action === "reject" || workflowEvent?.action === "request-revision"
        ? "attention"
        : workflowEvent
          ? workflow?.workOrder.status === "completed"
            ? "success"
            : "in-progress"
          : activity.outcome,
    evidenceIds: workflowEvent?.fieldEvidence
      ? [workflowEvent.fieldEvidence.artifactUri]
      : activity.evidenceIds,
    workflowRevision: workflow?.revision ?? null,
    workflowStatus: workflow?.mission.status ?? null,
  });
}
