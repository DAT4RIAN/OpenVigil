import assert from "node:assert/strict";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";

const contractUrl = new URL("../lib/server-workflow-contract.ts", import.meta.url);
contractUrl.searchParams.set("server-workflow-test", `${process.pid}-${Date.now()}`);
const {
  applyServerWorkflowMutation,
  authorizeServerWorkflowDemoActor,
  buildServerWorkflowFieldEvidence,
  initialServerWorkflowSnapshot,
  isSupportedServerWorkflowTurbineId,
  requireServerWorkflowPersistence,
  serverWorkflowTaskDefinitions,
} = await import(contractUrl.href);

const workerUrl = new URL("../dist/server/index.js", import.meta.url);
workerUrl.searchParams.set("server-workflow-store-test", `${process.pid}-${Date.now()}`);
const { default: worker } = await import(workerUrl.href);

class SQLiteD1Statement {
  constructor(database, sql, bindings = []) {
    this.database = database;
    this.sql = sql;
    this.bindings = bindings;
  }

  bind(...bindings) {
    return new SQLiteD1Statement(this.database, this.sql, bindings);
  }

  async first() {
    return this.database.prepare(this.sql).get(...this.bindings) ?? null;
  }

  async all() {
    return {
      success: true,
      results: this.database.prepare(this.sql).all(...this.bindings),
      meta: {},
    };
  }

  executeForBatch() {
    const statement = this.database.prepare(this.sql);
    if (/^\s*(?:SELECT|PRAGMA|WITH)\b/i.test(this.sql)) {
      return { success: true, results: statement.all(...this.bindings), meta: { changes: 0 } };
    }
    const result = statement.run(...this.bindings);
    return {
      success: true,
      results: [],
      meta: {
        changes: Number(result.changes),
        last_row_id: Number(result.lastInsertRowid),
      },
    };
  }
}

class SQLiteD1Database {
  constructor() {
    this.database = new DatabaseSync(":memory:");
    this.database.exec("PRAGMA foreign_keys=ON");
    this.batchTail = Promise.resolve();
  }

  prepare(sql) {
    return new SQLiteD1Statement(this.database, sql);
  }

  batch(statements) {
    const operation = this.batchTail.then(() => {
      this.database.exec("BEGIN IMMEDIATE");
      try {
        const results = statements.map((statement) => statement.executeForBatch());
        this.database.exec("COMMIT");
        return results;
      } catch (error) {
        this.database.exec("ROLLBACK");
        throw error;
      }
    });
    this.batchTail = operation.catch(() => undefined);
    return operation;
  }

  close() {
    this.database.close();
  }
}

const assets = { fetch: async () => new Response("Not found", { status: 404 }) };
const context = { waitUntil() {}, passThroughOnException() {} };

async function fetchApi(database, path, method = "GET", body) {
  const response = await worker.fetch(
    new Request(`http://localhost${path}`, {
      method,
      headers: {
        accept: "application/json",
        ...(body === undefined ? {} : { "content-type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
    { ASSETS: assets, DB: database },
    context,
  );
  return { response, body: await response.json() };
}

const fetchWorkflow = (database, method = "GET", body) =>
  fetchApi(database, "/api/workflow/WT-023", method, body);

test("server-owned demo principals canonicalize attribution and constrain actions", () => {
  assert.deepEqual(authorizeServerWorkflowDemoActor("demo-duty-chief", "approve"), {
    id: "demo-duty-chief",
    name: "李明远",
    role: "duty-chief-engineer",
  });
  assert.throws(
    () => authorizeServerWorkflowDemoActor("demo-maintenance-team", "approve"),
    (error) => error.code === "WORKFLOW_ACTOR_UNAUTHORIZED" && error.status === 403,
  );
  assert.throws(
    () => authorizeServerWorkflowDemoActor("caller-defined-admin", "reset"),
    (error) => error.code === "WORKFLOW_ACTOR_UNAUTHORIZED" && error.status === 403,
  );
});

const actor = {
  id: "operator-li",
  name: "Li Mingyuan",
  role: "Duty Chief Engineer",
};

const approvalActionNames = new Set(["approve", "reject", "request-revision", "escalate"]);

const mutation = (action, snapshot, idempotencyKey, extra = {}) => ({
  action,
  actor,
  expectedRevision: snapshot.revision,
  idempotencyKey,
  correlationId: `CORR-${idempotencyKey}`,
  ...(approvalActionNames.has(action) ? { selectedAlternativeId: "ALT-0823-B" } : {}),
  ...extra,
});

const apiActorIds = {
  approve: "demo-duty-chief",
  "start-work-order": "demo-maintenance-team",
  "set-task-completion": "demo-maintenance-team",
  "complete-work-order": "demo-verification-engineer",
};

const apiMutation = (action, snapshot, idempotencyKey, extra = {}) => ({
  ...mutation(action, snapshot, idempotencyKey, extra),
  actor: { id: apiActorIds[action], name: "Ignored caller label" },
  ...(action === "set-task-completion" && extra.completed
    ? {
        fieldEvidence: buildServerWorkflowFieldEvidence(extra.taskId, {
          id: "demo-maintenance-team",
          name: "Ignored caller label",
          role: "maintenance-execution",
        }),
      }
    : {}),
});

const fieldEvidence = (taskId) => buildServerWorkflowFieldEvidence(taskId, actor);

const apply = (snapshot, request, minute = snapshot.revision) =>
  applyServerWorkflowMutation(
    snapshot,
    request,
    `2026-08-13T12:${String(minute).padStart(2, "0")}:00Z`,
  );

test("the explicit no-D1 fallback is readable, immutable, and WT-023-only", async () => {
  const fallback = initialServerWorkflowSnapshot();
  assert.equal(fallback.revision, 0);
  assert.equal(fallback.decision.status, "under-review");
  assert.equal(fallback.workOrder.tasks.length, 5);
  assert.throws(
    () => requireServerWorkflowPersistence(false),
    (error) => error.code === "PERSISTENCE_UNAVAILABLE" && error.status === 503,
  );

  const storeSource = await import("node:fs/promises").then((fs) =>
    fs.readFile(new URL("../db/runtime-store.ts", import.meta.url), "utf8"),
  );
  assert.match(
    storeSource,
    /snapshot: initialServerWorkflowSnapshot\(\),\s+persistence: "ephemeral",\s+writable: false/,
  );

  assert.equal(isSupportedServerWorkflowTurbineId("WT-023"), true);
  assert.equal(isSupportedServerWorkflowTurbineId("wt-023"), true);
  assert.equal(isSupportedServerWorkflowTurbineId("WT-024"), false);
});

test("the workflow route only accepts the three declared alternatives for approval review", async (t) => {
  const database = new SQLiteD1Database();
  t.after(() => database.close());
  const snapshot = (await fetchWorkflow(database)).body.data;
  const base = apiMutation("approve", snapshot, "invalid-alternative", {
    reason: "Review complete",
    comment: "Attempt an unknown plan",
  });

  for (const selectedAlternativeId of [undefined, "ALT-0823-D"]) {
    const result = await fetchWorkflow(database, "POST", {
      ...base,
      selectedAlternativeId,
      idempotencyKey: `invalid-alternative-${selectedAlternativeId ?? "missing"}`,
    });
    assert.equal(result.response.status, 400);
    assert.equal(result.body.error.code, "APPROVAL_ALTERNATIVE_REQUIRED");
  }
});

test("WT-023 high-risk execution stays behind recorded human approval", () => {
  const initial = initialServerWorkflowSnapshot();
  assert.throws(
    () => apply(initial, mutation("start-work-order", initial, "start-before-approval")),
    (error) => error.code === "HUMAN_APPROVAL_REQUIRED" && error.status === 409,
  );

  const approved = apply(
    initial,
    mutation("approve", initial, "approve", {
      reason: "SCADA, CMS, and historical evidence agree",
      comment: "Approve alternative B with the shutdown threshold retained",
    }),
  );
  assert.equal(approved.revision, 1);
  assert.equal(approved.mission.status, "approved");
  assert.equal(approved.decision.status, "approved");
  assert.equal(approved.decision.approval.action, "approve");
  assert.equal(approved.decision.approval.selectedAlternativeId, "ALT-0823-B");
  assert.equal(approved.workOrder.alternativeId, "ALT-0823-B");
  assert.equal(approved.workOrder.status, "scheduled");

  const started = apply(approved, mutation("start-work-order", approved, "start"));
  assert.equal(started.mission.status, "executing");
  assert.equal(started.workOrder.status, "in-progress");
});

test("an explicit alternative selection drives approval audit and the generated work order", () => {
  const initial = initialServerWorkflowSnapshot();
  const approved = apply(
    initial,
    mutation("approve", initial, "approve-plan-a", {
      selectedAlternativeId: "ALT-0823-A",
      reason: "Immediate shutdown has been selected",
      comment: "Approve plan A",
    }),
  );

  assert.equal(approved.decision.selectedAlternativeId, "ALT-0823-A");
  assert.equal(approved.workOrder.alternativeId, "ALT-0823-A");
  assert.match(approved.workOrder.tasks[0].title, /立即停机/);
  assert.equal(approved.auditEvents[0].toState.selectedAlternativeId, "ALT-0823-A");
  assert.equal(approved.auditEvents[0].toState.workOrderAlternativeId, "ALT-0823-A");
  assert.match(approved.auditEvents[0].detail, /方案 A/);
  assert.match(approved.auditEvents[0].detail, /ALT-0823-A/);
});

test("five explicit task completions gate closure, health feedback, and knowledge capture", () => {
  let snapshot = initialServerWorkflowSnapshot();
  snapshot = apply(
    snapshot,
    mutation("approve", snapshot, "approve-loop", {
      reason: "Evidence is complete",
      comment: "Approved",
    }),
  );
  snapshot = apply(snapshot, mutation("start-work-order", snapshot, "start-loop"));

  assert.throws(
    () => apply(snapshot, mutation("complete-work-order", snapshot, "premature")),
    (error) => error.code === "TASK_GATE_BLOCKED" && error.status === 409,
  );
  assert.throws(
    () =>
      apply(
        snapshot,
        mutation("set-task-completion", snapshot, "missing-field-evidence", {
          taskId: snapshot.workOrder.tasks[0].id,
          completed: true,
        }),
      ),
    (error) => error.code === "FIELD_EVIDENCE_REQUIRED" && error.status === 400,
  );

  for (const [index, task] of snapshot.workOrder.tasks.entries()) {
    snapshot = apply(
      snapshot,
      mutation("set-task-completion", snapshot, `task-${index + 1}`, {
        taskId: task.id,
        completed: true,
        fieldEvidence: fieldEvidence(task.id),
      }),
    );
    assert.equal(snapshot.workOrder.completedTaskCount, index + 1);
    const completedTask = snapshot.workOrder.tasks.find(({ id }) => id === task.id);
    assert.equal(completedTask.fieldEvidence.verificationMode, "deterministic-fixture");
    assert.match(completedTask.fieldEvidence.artifactUri, /^fixture:\/\/windops-field-evidence\//);
    assert.match(completedTask.fieldEvidence.artifactSha256, /^[a-f0-9]{64}$/);
    assert.equal(completedTask.fieldEvidence.verifiedBy.id, actor.id);
    assert.equal(
      snapshot.auditEvents.at(-1).fieldEvidence.artifactUri,
      completedTask.fieldEvidence.artifactUri,
    );
  }

  const closed = apply(snapshot, mutation("complete-work-order", snapshot, "complete-after-five"));
  assert.equal(closed.revision, 8);
  assert.equal(closed.mission.status, "completed");
  assert.equal(closed.workOrder.status, "completed");
  assert.deepEqual(closed.health, { turbineScore: 82, mainBearingScore: 78 });
  assert.equal(closed.knowledgeCaseId, "KB-CASE-2026-WT023-CLOSED");
  assert.deepEqual(
    closed.auditEvents.slice(-2).map((event) => [event.revision, event.eventSequence, event.kind]),
    [
      [8, 1, "verification"],
      [8, 2, "knowledge"],
    ],
  );
});

test("optimistic revisions reject stale writers without mutating the snapshot", () => {
  const initial = initialServerWorkflowSnapshot();
  const approved = apply(
    initial,
    mutation("approve", initial, "revision-approve", {
      reason: "Evidence is complete",
      comment: "Approved",
    }),
  );
  const stale = {
    ...mutation("start-work-order", approved, "stale-start"),
    expectedRevision: 0,
  };
  assert.throws(
    () => apply(approved, stale),
    (error) =>
      error.code === "REVISION_CONFLICT" &&
      error.details.currentRevision === 1 &&
      error.details.expectedRevision === 0,
  );
  assert.equal(approved.revision, 1);
  assert.equal(approved.auditEvents.length, 1);
  assert.equal(approved.workOrder.completedTaskCount, 0);
});

test("reset restores the review baseline while retaining append-only audit history", () => {
  let snapshot = initialServerWorkflowSnapshot();
  snapshot = apply(
    snapshot,
    mutation("approve", snapshot, "reset-approve", {
      reason: "Evidence is complete",
      comment: "Approved",
    }),
  );
  snapshot = apply(snapshot, mutation("start-work-order", snapshot, "reset-start"));
  snapshot = apply(
    snapshot,
    mutation("set-task-completion", snapshot, "reset-task", {
      taskId: serverWorkflowTaskDefinitions[0].id,
      completed: true,
      fieldEvidence: fieldEvidence(serverWorkflowTaskDefinitions[0].id),
    }),
  );

  const reset = apply(snapshot, mutation("reset", snapshot, "reset-action"));
  assert.equal(reset.revision, 4);
  assert.equal(reset.decision.status, "under-review");
  assert.equal(reset.decision.approval, null);
  assert.equal(reset.workOrder.status, "draft");
  assert.equal(reset.workOrder.completedTaskCount, 0);
  assert.deepEqual(reset.health, { turbineScore: 68, mainBearingScore: 63 });
  assert.equal(reset.knowledgeCaseId, null);
  assert.equal(reset.auditEvents.length, 4);
  assert.equal(reset.auditEvents.at(-1).kind, "reset");
});

test("reject, revision, and escalation outcomes obey the state machine", () => {
  const scenarios = [
    ["escalate", "under-review", "under-review"],
    ["request-revision", "diagnosed", "revision-requested"],
    ["reject", "decision-pending", "rejected"],
  ];

  for (const [action, missionStatus, decisionStatus] of scenarios) {
    const initial = initialServerWorkflowSnapshot();
    const result = apply(
      initial,
      mutation(action, initial, `outcome-${action}`, {
        reason: "Human review outcome",
        comment: `Execute ${action}`,
      }),
    );
    assert.equal(result.mission.status, missionStatus);
    assert.equal(result.decision.status, decisionStatus);
    assert.equal(result.workOrder.status, "draft");
    if (action !== "escalate") {
      assert.throws(
        () =>
          apply(
            result,
            mutation(action, result, `illegal-${action}`, {
              reason: "Repeat",
              comment: "Must be rejected",
            }),
          ),
        (error) => error.code === "ILLEGAL_TRANSITION",
      );
    }
  }
});

test("D1 storage serializes a consistent snapshot, rejects a stale CAS writer, and preserves tasks", async (t) => {
  const database = new SQLiteD1Database();
  t.after(() => database.close());

  let snapshot = (await fetchWorkflow(database)).body.data;
  let result = await fetchWorkflow(
    database,
    "POST",
    apiMutation("approve", snapshot, "store-approve", {
      selectedAlternativeId: "ALT-0823-A",
      reason: "Evidence is complete",
      comment: "Approved for durable execution",
    }),
  );
  assert.equal(result.response.status, 200);
  snapshot = result.body.data;
  assert.equal(snapshot.decision.approval.selectedAlternativeId, "ALT-0823-A");
  assert.equal(snapshot.workOrder.alternativeId, "ALT-0823-A");
  assert.match(snapshot.workOrder.tasks[0].title, /立即停机/);
  result = await fetchWorkflow(
    database,
    "POST",
    apiMutation("start-work-order", snapshot, "store-start"),
  );
  assert.equal(result.response.status, 200);
  snapshot = result.body.data;

  const competingRequests = serverWorkflowTaskDefinitions.slice(0, 2).map((task, index) =>
    apiMutation("set-task-completion", snapshot, `store-concurrent-${index + 1}`, {
      taskId: task.id,
      completed: true,
    }),
  );
  const outcomes = await Promise.all([
    fetchWorkflow(database, "POST", competingRequests[0]),
    fetchWorkflow(database, "POST", competingRequests[1]),
  ]);

  assert.deepEqual(outcomes.map(({ response }) => response.status).sort(), [200, 409]);
  const rejected = outcomes.find(({ response }) => response.status === 409);
  assert.equal(rejected.body.error.code, "REVISION_CONFLICT");

  snapshot = (await fetchWorkflow(database)).body.data;
  assert.equal(snapshot.revision, 3);
  assert.equal(snapshot.decision.approval.selectedAlternativeId, "ALT-0823-A");
  assert.equal(snapshot.workOrder.alternativeId, "ALT-0823-A");
  assert.match(snapshot.workOrder.tasks[0].title, /立即停机/);
  assert.equal(snapshot.workOrder.completedTaskCount, 1);
  const completedIds = snapshot.workOrder.tasks
    .filter((task) => task.completed)
    .map((task) => task.id);
  assert.equal(completedIds.length, 1);
  assert.ok(serverWorkflowTaskDefinitions.slice(0, 2).some((task) => task.id === completedIds[0]));
  assert.equal(
    database.database.prepare("SELECT COUNT(*) AS count FROM workflow_audit_events").get().count,
    3,
  );
  assert.equal(
    database.database.prepare("SELECT COUNT(*) AS count FROM workflow_idempotency").get().count,
    3,
  );

  const remainingTask = serverWorkflowTaskDefinitions
    .slice(0, 2)
    .find((task) => task.id !== completedIds[0]);
  const retryRequest = apiMutation("set-task-completion", snapshot, "store-retry-missing-task", {
    taskId: remainingTask.id,
    completed: true,
  });
  const committed = await fetchWorkflow(database, "POST", retryRequest);
  const replay = await fetchWorkflow(database, "POST", retryRequest);

  assert.equal(committed.response.status, 200);
  assert.equal(committed.body.meta.replayed, false);
  assert.equal(replay.response.status, 200);
  assert.equal(replay.body.meta.replayed, true);
  assert.deepEqual(replay.body.data, committed.body.data);
  assert.equal(committed.body.data.workOrder.completedTaskCount, 2);
  assert.ok(
    serverWorkflowTaskDefinitions
      .slice(0, 2)
      .every(
        (task) => committed.body.data.workOrder.tasks.find(({ id }) => id === task.id).completed,
      ),
  );
  assert.equal(
    database.database.prepare("SELECT COUNT(*) AS count FROM workflow_audit_events").get().count,
    4,
  );
  assert.equal(
    database.database.prepare("SELECT COUNT(*) AS count FROM workflow_idempotency").get().count,
    4,
  );
  assert.deepEqual(database.database.prepare("PRAGMA foreign_key_check").all(), []);
});

test("closed WT-023 state is shared by predictive, knowledge, and audited Agent Tool APIs", async (t) => {
  const database = new SQLiteD1Database();
  t.after(() => database.close());

  let snapshot = (await fetchWorkflow(database)).body.data;
  for (const request of [
    apiMutation("approve", snapshot, "overlay-approve", {
      reason: "Evidence, resources, and weather window verified",
      comment: "Approve alternative B",
    }),
  ]) {
    const result = await fetchWorkflow(database, "POST", request);
    assert.equal(result.response.status, 200, JSON.stringify(result.body));
    snapshot = result.body.data;
  }
  const [approvedMissions, approvedDecisions, approvedAgents] = await Promise.all([
    fetchApi(database, "/api/missions"),
    fetchApi(database, "/api/decisions"),
    fetchApi(database, "/api/agents"),
  ]);
  const approvedMission = approvedMissions.body.data.find(({ id }) => id === "MISSION-2026-0823");
  const approvedDecision = approvedDecisions.body.data.find(
    ({ id }) => id === "DECISION-2026-0823",
  );
  assert.match(approvedMission.summary, /人工批准/);
  assert.match(approvedMission.nextAction, /WO-20260823-017/);
  assert.equal(approvedDecision.status, "approved");
  assert.equal(approvedDecision.approval.approver, "李明远");
  assert.ok(
    approvedAgents.body.data
      .filter(({ currentMissionId }) => currentMissionId === approvedMission.id)
      .every(({ currentTask }) => currentTask?.includes("已批准")),
  );

  let result = await fetchWorkflow(
    database,
    "POST",
    apiMutation("start-work-order", snapshot, "overlay-start"),
  );
  assert.equal(result.response.status, 200, JSON.stringify(result.body));
  snapshot = result.body.data;
  const executingMissions = await fetchApi(database, "/api/missions");
  const executingMission = executingMissions.body.data.find(({ id }) => id === "MISSION-2026-0823");
  assert.match(executingMission.summary, /正在执行/);
  assert.match(executingMission.nextAction, /现场任务/);
  for (const [index, task] of snapshot.workOrder.tasks.entries()) {
    result = await fetchWorkflow(
      database,
      "POST",
      apiMutation("set-task-completion", snapshot, `overlay-task-${index + 1}`, {
        taskId: task.id,
        completed: true,
      }),
    );
    assert.equal(result.response.status, 200, JSON.stringify(result.body));
    snapshot = result.body.data;
  }
  result = await fetchWorkflow(
    database,
    "POST",
    apiMutation("complete-work-order", snapshot, "overlay-complete"),
  );
  assert.equal(result.response.status, 200, JSON.stringify(result.body));
  snapshot = result.body.data;
  assert.equal(snapshot.revision, 8);

  const [
    missionCollection,
    decisionCollection,
    evidenceCollection,
    alarmCollection,
    agentCollection,
  ] = await Promise.all([
    fetchApi(database, "/api/missions"),
    fetchApi(database, "/api/decisions"),
    fetchApi(database, "/api/evidence"),
    fetchApi(database, "/api/alarms"),
    fetchApi(database, "/api/agents"),
  ]);
  for (const collection of [
    missionCollection,
    decisionCollection,
    evidenceCollection,
    alarmCollection,
    agentCollection,
  ]) {
    assert.equal(collection.response.status, 200, JSON.stringify(collection.body));
    assert.equal(collection.body.meta.workflowPersistence, "d1");
    assert.equal(collection.body.meta.workflowRevision, snapshot.revision);
    assert.equal(collection.body.meta.snapshotAt, snapshot.updatedAt);
  }

  const mission = missionCollection.body.data.find(({ id }) => id === "MISSION-2026-0823");
  const decision = decisionCollection.body.data.find(({ id }) => id === "DECISION-2026-0823");
  const relatedEvidence = evidenceCollection.body.data.filter(
    ({ missionId }) => missionId === mission.id,
  );
  const relatedAlarms = alarmCollection.body.data.filter(
    ({ missionId }) => missionId === mission.id,
  );
  const relatedAgents = agentCollection.body.data.filter(
    ({ currentMissionId }) => currentMissionId === mission.id,
  );

  assert.equal(mission.status, "completed");
  assert.match(mission.summary, /完成现场检查与复测/);
  assert.match(mission.nextAction, /KB-CASE-2026-WT023-CLOSED/);
  assert.equal(decision.status, "approved");
  assert.deepEqual(decision.approval, {
    required: true,
    action: "approve",
    selectedAlternativeId: "ALT-0823-B",
    approver: "李明远",
    approverRole: "duty-chief-engineer",
    timestamp: snapshot.decision.approval.timestamp,
    reason: "Evidence, resources, and weather window verified",
    comment: "Approve alternative B",
  });
  assert.deepEqual(new Set(relatedEvidence.map(({ id }) => id)), new Set(decision.evidenceIds));
  assert.deepEqual(new Set(relatedAlarms.map(({ id }) => id)), new Set(mission.alarmIds));
  assert.ok(
    relatedAlarms.every(
      ({ status, resolvedAt }) => status === "resolved" && resolvedAt === snapshot.updatedAt,
    ),
  );
  assert.deepEqual(new Set(relatedAgents.map(({ id }) => id)), new Set(mission.agentIds));
  assert.ok(relatedAgents.every(({ status, currentTask }) => status === "idle" && !currentTask));
  assert.equal(
    database.database.prepare("SELECT COUNT(*) AS count FROM workflow_audit_events").get().count,
    9,
    "read overlays must not delete or rewrite append-only workflow audit history",
  );

  const predictive = await fetchApi(database, "/api/predictive-assessments?turbineId=WT-023");
  assert.equal(predictive.response.status, 200);
  assert.equal(predictive.body.data[0].healthScore, 82);
  assert.equal(predictive.body.data[0].componentHealth, 78);
  assert.equal(predictive.body.data[0].anomalyScore, 0.42);
  assert.equal(predictive.body.data[0].failureProbability30d, undefined);
  assert.equal(predictive.body.data[0].remainingUsefulLifeDays, undefined);
  assert.equal(predictive.body.meta.workflowRevision, 8);

  const knowledge = await fetchApi(database, "/api/knowledge-assistant", "POST", {
    question: "WT-023 闭环后有哪些验证证据？",
    turbineId: "WT-023",
    missionId: "MISSION-2026-0823",
  });
  assert.equal(knowledge.response.status, 200, JSON.stringify(knowledge.body));
  assert.equal(knowledge.body.meta.knowledgeCaseId, "KB-CASE-2026-WT023-CLOSED");
  assert.equal(knowledge.body.data.answer.citations[0].docId, "KB-CASE-2026-WT023-CLOSED");
  assert.match(knowledge.body.data.answer.answer.conclusion, /82/);
  assert.match(knowledge.body.data.answer.answer.conclusion, /78/);

  const tool = await fetchApi(database, "/api/agent-tools", "POST", {
    tool: "get_turbine_status",
    args: { turbineId: "WT-023" },
    agentId: "agent-scada-analysis",
    missionId: "MISSION-2026-0823",
    idempotencyKey: "overlay-tool-health",
  });
  assert.equal(tool.response.status, 200, JSON.stringify(tool.body));
  assert.equal(tool.body.data.execution.result.data.snapshotAt, snapshot.updatedAt);
  assert.equal(tool.body.data.execution.result.data.turbine.healthScore, 82);
  assert.equal(tool.body.data.execution.result.data.subsystemSummary.lowest.healthScore, 78);
  assert.deepEqual(tool.body.data.execution.result.data.activeMissionIds, []);

  const ledgerCount = database.database
    .prepare("SELECT COUNT(*) AS count FROM agent_executions")
    .get().count;
  const mismatch = await fetchApi(database, "/api/agent-tools", "POST", {
    tool: "query_work_orders",
    args: { workOrderId: "WO-20260811-012" },
    agentId: "agent-maintenance-strategy",
    missionId: "MISSION-2026-0823",
    idempotencyKey: "overlay-mismatched-work-order",
  });
  assert.equal(mismatch.response.status, 422);
  assert.equal(mismatch.body.error.code, "MISSION_CONTEXT_MISMATCH");
  assert.equal(
    database.database.prepare("SELECT COUNT(*) AS count FROM agent_executions").get().count,
    ledgerCount,
  );
});

test("the D1 store uses single-statement prepared batches and atomic revision guards", async () => {
  const source = await import("node:fs/promises").then((fs) =>
    fs.readFile(new URL("../db/runtime-store.ts", import.meta.url), "utf8"),
  );
  const migration = await import("node:fs/promises").then((fs) =>
    fs.readFile(new URL("../drizzle/0002_server_workflow.sql", import.meta.url), "utf8"),
  );

  assert.match(source, /new WeakMap<D1Database, Promise<void>>\(\)/);
  assert.match(source, /database\.batch\(CREATE_STATEMENTS\.map/);
  assert.match(
    source,
    /const \[instanceResult, tasksResult, auditResult\] = await database\.batch/,
  );
  assert.doesNotMatch(source, /const \[instance, tasksResult, auditResult\] = await Promise\.all/);
  assert.doesNotMatch(source, /database\.exec\(/);
  assert.match(source, /WHERE mission_id = \? AND revision = \?/);
  assert.match(source, /CREATE TRIGGER IF NOT EXISTS workflow_audit_revision_guard/);
  assert.match(source, /RAISE\(ABORT, 'workflow revision conflict'\)/);
  assert.match(migration, /CREATE TRIGGER `workflow_audit_revision_guard`/);
  assert.match(
    migration,
    /CREATE UNIQUE INDEX `workflow_audit_mission_revision_sequence_uidx` ON `workflow_audit_events` \(`mission_id`,`revision`,`event_sequence`\)/,
  );
});
