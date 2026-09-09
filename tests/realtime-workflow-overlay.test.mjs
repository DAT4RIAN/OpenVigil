import assert from "node:assert/strict";
import test from "node:test";
const { realtimeAgentActivityData, realtimeAlarmData, selectRealtimeAlarm } = await import(
  new URL("../lib/realtime-workflow-overlay.ts", import.meta.url).href
);
const {
  applyServerWorkflowMutation,
  initialServerWorkflowSnapshot,
  buildServerWorkflowFieldEvidence,
} = await import(new URL("../lib/server-workflow-contract.ts", import.meta.url).href);

const actor = { id: "demo-duty-chief", name: "李明远", role: "duty-chief-engineer" };
const mutate = (snapshot, action, key, extra = {}, mutationActor = actor) =>
  applyServerWorkflowMutation(
    snapshot,
    {
      action,
      actor: mutationActor,
      expectedRevision: snapshot.revision,
      idempotencyKey: key,
      correlationId: `CORR-${key}`,
      ...extra,
    },
    `2026-08-13T06:${String(snapshot.revision).padStart(2, "0")}:00Z`,
  );

test("alarm and Agent realtime frames derive workflow state from the same server snapshot", () => {
  let snapshot = initialServerWorkflowSnapshot();
  snapshot = mutate(snapshot, "approve", "rt-approve", {
    selectedAlternativeId: "ALT-0823-B",
    reason: "Evidence verified",
    comment: "Proceed with guarded plan",
  });

  const fixtureActivity = {
    id: "ACTIVITY-FIXTURE",
    missionId: snapshot.mission.id,
    agentId: "agent-fixture",
    actorLabel: "Fixture Agent",
    kind: "analysis",
    title: "fixture",
    detail: "fixture",
    timestamp: snapshot.updatedAt,
    outcome: "in-progress",
    evidenceIds: [],
  };
  const activityData = realtimeAgentActivityData(fixtureActivity, 0, snapshot);
  assert.equal(activityData.workflowRevision, snapshot.revision);
  assert.equal(activityData.workflowStatus, snapshot.mission.status);
  assert.equal(activityData.id, snapshot.auditEvents[0].id);
  assert.equal(activityData.kind, "approval");

  snapshot = mutate(
    snapshot,
    "start-work-order",
    "rt-start",
    {},
    { id: "demo-maintenance-team", name: "海维二组", role: "maintenance-execution" },
  );
  for (const task of snapshot.workOrder.tasks) {
    const fieldActor = {
      id: "demo-maintenance-team",
      name: "海维二组",
      role: "maintenance-execution",
    };
    snapshot = mutate(
      snapshot,
      "set-task-completion",
      `rt-${task.id}`,
      {
        taskId: task.id,
        completed: true,
        fieldEvidence: buildServerWorkflowFieldEvidence(task.id, fieldActor),
      },
      fieldActor,
    );
  }
  snapshot = mutate(
    snapshot,
    "complete-work-order",
    "rt-close",
    {},
    { id: "demo-verification-engineer", name: "林工", role: "maintenance-verification" },
  );
  const fixtureAlarm = {
    id: "ALARM-FIXTURE",
    code: "FIXTURE",
    turbineId: snapshot.turbineId,
    subsystem: "main-bearing",
    severity: "critical",
    title: "fixture",
    description: "fixture",
    triggeredAt: snapshot.updatedAt,
    durationMinutes: 1,
    status: "active",
    aiStatus: "diagnosed",
    assignee: null,
    acknowledgedAt: null,
    resolvedAt: null,
    currentValue: 1,
    threshold: 1,
    unit: "mm/s",
    missionId: snapshot.mission.id,
    evidenceIds: [],
  };
  const alarm = selectRealtimeAlarm([fixtureAlarm], 0, snapshot);
  assert.equal(alarm.missionId, snapshot.mission.id);
  assert.equal(alarm.status, "resolved");
  assert.equal(alarm.assignee, null);
  assert.equal(alarm.acknowledgedAt, snapshot.updatedAt);
  assert.equal(alarm.resolvedAt, snapshot.updatedAt);
  assert.deepEqual(realtimeAlarmData(alarm), {
    id: alarm.id,
    turbineId: alarm.turbineId,
    severity: alarm.severity,
    status: "resolved",
    assignee: null,
    acknowledgedAt: snapshot.updatedAt,
    resolvedAt: snapshot.updatedAt,
    title: alarm.title,
    missionId: snapshot.mission.id,
    currentValue: alarm.currentValue,
    threshold: alarm.threshold,
    unit: alarm.unit,
  });
});
