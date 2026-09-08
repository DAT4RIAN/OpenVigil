import assert from "node:assert/strict";
import test from "node:test";

const workerUrl = new URL("../dist/server/index.js", import.meta.url);
workerUrl.searchParams.set("agent-tools-test", `${process.pid}-${Date.now()}`);
const { default: worker } = await import(workerUrl.href);

const environment = {
  ASSETS: {
    fetch: async () => new Response("Not found", { status: 404 }),
  },
};

const context = {
  waitUntil() {},
  passThroughOnException() {},
};

const request = (method, body) =>
  worker.fetch(
    new Request("http://localhost/api/agent-tools", {
      method,
      headers: {
        accept: "application/json",
        ...(body === undefined ? {} : { "content-type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
    environment,
    context,
  );

async function jsonRequest(method, body, expectedStatus = 200) {
  const response = await request(method, body);
  assert.equal(response.status, expectedStatus);
  assert.match(response.headers.get("content-type") ?? "", /^application\/json\b/i);
  return response.json();
}

test("deterministic Agent Tool API validates, executes, links, and records every declared tool", async (t) => {
  await t.test("catalog starts with an empty deterministic runtime history", async () => {
    const response = await jsonRequest("GET");
    assert.equal(response.ok, true);
    assert.equal(response.error, null);
    assert.equal(response.meta.deterministic, true);
    assert.equal(response.meta.persisted, false);
    assert.equal(response.data.catalog.length, 17);
    assert.deepEqual(response.data.executionHistory, []);

    const names = response.data.catalog.map((entry) => entry.name);
    assert.deepEqual(names, [
      "get_turbine_status",
      "query_scada",
      "query_alarm_history",
      "query_vibration",
      "query_weather",
      "query_maintenance_history",
      "query_similar_failures",
      "calculate_health_score",
      "predict_rul",
      "create_decision",
      "create_work_order",
      "query_manual",
      "query_work_orders",
      "query_spare_parts",
      "query_crew",
      "query_vessels",
      "update_work_order",
    ]);

    const nonReadOnly = response.data.catalog
      .filter((entry) => !entry.readOnly)
      .map((entry) => entry.name);
    assert.deepEqual(nonReadOnly, ["create_decision", "create_work_order", "update_work_order"]);
    assert.ok(
      response.data.catalog
        .filter((entry) => nonReadOnly.includes(entry.name))
        .every((entry) => entry.dryRun === true),
    );
  });

  await t.test(
    "unknown tools and malformed args use one error envelope and are not executed",
    async () => {
      const unknown = await jsonRequest("POST", { tool: "restart_turbine", args: {} }, 400);
      assert.equal(unknown.ok, false);
      assert.equal(unknown.data, null);
      assert.equal(unknown.error.code, "UNKNOWN_AGENT_TOOL");
      assert.equal(unknown.meta.historyCount, 0);

      const invalid = await jsonRequest("POST", { tool: "get_turbine_status", args: {} }, 422);
      assert.equal(invalid.ok, false);
      assert.equal(invalid.data, null);
      assert.equal(invalid.error.code, "INVALID_TOOL_ARGUMENTS");
      assert.equal(invalid.meta.historyCount, 0);

      const invalidManual = await jsonRequest(
        "POST",
        { tool: "query_manual", args: { query: 23 } },
        422,
      );
      assert.equal(invalidManual.error.code, "INVALID_TOOL_ARGUMENTS");
      assert.equal(invalidManual.error.details.argument, "query");

      const invalidBoolean = await jsonRequest(
        "POST",
        { tool: "query_work_orders", args: { includeHistorical: "yes" } },
        422,
      );
      assert.equal(invalidBoolean.error.code, "INVALID_TOOL_ARGUMENTS");
      assert.equal(invalidBoolean.error.details.argument, "includeHistorical");

      const statusMutation = await jsonRequest(
        "POST",
        {
          tool: "update_work_order",
          args: { workOrderId: "WO-20260823-017", status: "completed", dryRun: true },
        },
        422,
      );
      assert.equal(statusMutation.error.code, "INVALID_TOOL_ARGUMENTS");
      assert.deepEqual(statusMutation.error.details.unknownKeys, ["status"]);

      const persistenceAttempt = await jsonRequest(
        "POST",
        {
          tool: "update_work_order",
          args: {
            workOrderId: "WO-20260823-017",
            assignedTeam: "Unapproved reassignment",
            dryRun: false,
          },
        },
        422,
      );
      assert.equal(persistenceAttempt.error.code, "INVALID_TOOL_ARGUMENTS");
      assert.equal(persistenceAttempt.error.details.acceptedValue, true);
      assert.equal(persistenceAttempt.meta.historyCount, 0);
    },
  );

  const calls = [
    ["get_turbine_status", { turbineId: "wt-023" }],
    ["query_scada", { turbineId: "WT-023", metric: "main-bearing-temperature", limit: 8 }],
    ["query_alarm_history", { turbineId: "WT-023", limit: 20 }],
    ["query_vibration", { turbineId: "WT-023", limit: 12 }],
    ["query_weather", { farmId: "WF-EAST-CHINA-01", limit: 5 }],
    ["query_maintenance_history", { turbineId: "WT-023", limit: 10 }],
    ["query_similar_failures", { turbineId: "WT-023", subsystem: "main-bearing", limit: 5 }],
    ["calculate_health_score", { turbineId: "WT-023" }],
    ["predict_rul", { turbineId: "WT-023", subsystem: "main-bearing" }],
    ["create_decision", { missionId: "MISSION-2026-0823", dryRun: true }],
    [
      "create_work_order",
      {
        missionId: "MISSION-2026-0823",
        decisionId: "DECISION-2026-0823",
        dryRun: true,
      },
    ],
    ["query_manual", { query: "WT-023", turbineId: "WT-023", limit: 8 }],
    ["query_work_orders", { turbineId: "WT-023", includeHistorical: true, limit: 20 }],
    ["query_spare_parts", { turbineId: "WT-023", limit: 20 }],
    ["query_crew", { turbineId: "WT-023", limit: 20 }],
    ["query_vessels", { turbineId: "WT-023", limit: 20 }],
    [
      "update_work_order",
      {
        workOrderId: "WO-20260823-017",
        assignedTeam: "Offshore Maintenance Team 2 / dry-run",
        plannedStart: "2026-08-14T09:00:00+08:00",
        deadline: "2026-08-14T17:00:00+08:00",
        note: "Validate crew and vessel synchronization without persistence.",
        dryRun: true,
      },
    ],
  ];

  const results = new Map();

  await t.test(
    "all seventeen tools execute against fixtures with complete observability records",
    async () => {
      for (const [tool, args] of calls) {
        const response = await jsonRequest("POST", { tool, args, persist: false });
        assert.equal(response.ok, true, `${tool} should succeed`);
        assert.equal(response.error, null);
        assert.equal(response.meta.deterministic, true);
        assert.equal(response.meta.persisted, false);

        const execution = response.data.execution;
        assert.equal(execution.request.tool, tool);
        assert.match(execution.executionId, /^AGEXEC-[0-9A-F]{64}$/);
        assert.match(execution.agentId, /^agent-/);
        assert.equal(typeof execution.idempotencyKey, "string");
        assert.match(execution.requestFingerprint, /^[0-9a-f]{64}$/);
        assert.equal(execution.status, "succeeded");
        assert.equal(execution.result.ok, true);
        assert.equal(
          execution.result.dryRun,
          ["create_decision", "create_work_order", "update_work_order"].includes(tool),
        );
        assert.equal(execution.deterministic, true);
        assert.match(
          execution.correlationId,
          new RegExp(`^WOPS-${tool.toUpperCase()}-AGEXEC-[0-9A-F]{64}$`),
        );
        assert.match(execution.startedAt, /^2026-08-13T/);
        assert.match(execution.completedAt, /^2026-08-13T/);
        assert.equal(
          Date.parse(execution.completedAt) - Date.parse(execution.startedAt),
          execution.latencyMs,
        );
        assert.ok(execution.latencyMs > 0);
        assert.ok(execution.tokenEstimate.input > 0);
        assert.ok(execution.tokenEstimate.output > 0);
        assert.equal(
          execution.tokenEstimate.total,
          execution.tokenEstimate.input + execution.tokenEstimate.output,
        );
        assert.equal(execution.tokenEstimate.method, "utf8-bytes-div-4");
        results.set(tool, execution.result.data);
      }
    },
  );

  await t.test("WT-023 retains its alarm-to-mission-to-decision-to-work-order linkage", () => {
    const status = results.get("get_turbine_status");
    assert.equal(status.turbine.id, "WT-023");
    assert.equal(status.subsystemSummary.lowest.subsystem, "main-bearing");
    assert.ok(status.activeMissionIds.includes("MISSION-2026-0823"));
    assert.ok(status.activeAlarms.some((alarm) => alarm.missionId === "MISSION-2026-0823"));

    const scada = results.get("query_scada");
    assert.equal(scada.turbineId, "WT-023");
    assert.equal(scada.metric, "main-bearing-temperature");
    assert.ok(scada.measurements.every((measurement) => measurement.turbineId === "WT-023"));

    const vibration = results.get("query_vibration");
    assert.equal(vibration.turbineId, "WT-023");
    assert.equal(vibration.metric, "main-bearing-vibration-rms");

    const health = results.get("calculate_health_score");
    assert.equal(health.healthScore, 68);
    assert.equal(health.fixtureHealthScore, 68);

    const rul = results.get("predict_rul");
    assert.equal(rul.turbineId, "WT-023");
    assert.equal(rul.subsystem, "main-bearing");
    assert.equal(rul.predictedRulDays, 47);

    const decision = results.get("create_decision");
    assert.equal(decision.dryRun, true);
    assert.equal(decision.persisted, false);
    assert.equal(decision.draft.missionId, "MISSION-2026-0823");
    assert.equal(decision.draft.turbineId, "WT-023");
    assert.equal(decision.draft.sourceDecisionId, "DECISION-2026-0823");

    const workOrder = results.get("create_work_order");
    assert.equal(workOrder.dryRun, true);
    assert.equal(workOrder.persisted, false);
    assert.equal(workOrder.draft.relatedMissionId, "MISSION-2026-0823");
    assert.equal(workOrder.draft.decisionId, "DECISION-2026-0823");
    assert.equal(workOrder.draft.turbineId, "WT-023");
    assert.equal(workOrder.draft.sourceWorkOrderId, "WO-20260823-017");
  });

  await t.test("knowledge, work-order, and resource tools resolve the WT-023 field package", () => {
    const manual = results.get("query_manual");
    assert.equal(manual.filters.turbineId, "WT-023");
    assert.ok(manual.documents.length > 0);
    assert.ok(
      manual.documents.every(
        (document) =>
          document.citation.documentId === document.id &&
          document.relatedTurbineIds.includes("WT-023"),
      ),
    );

    const workOrderQuery = results.get("query_work_orders");
    const featuredWorkOrder = workOrderQuery.workOrders.find(
      (workOrder) => workOrder.id === "WO-20260823-017",
    );
    assert.ok(featuredWorkOrder);
    assert.equal(featuredWorkOrder.turbineId, "WT-023");

    const parts = results.get("query_spare_parts");
    assert.ok(parts.scope.linkedWorkOrderIds.includes("WO-20260823-017"));
    assert.ok(parts.spareParts.some((part) => part.partNumber === "GB-MB-165-01"));
    assert.ok(
      parts.spareParts.every((part) =>
        part.reservedForWorkOrderIds.some((id) => parts.scope.linkedWorkOrderIds.includes(id)),
      ),
    );

    const crew = results.get("query_crew");
    assert.ok(crew.scope.linkedWorkOrderIds.includes("WO-20260823-017"));
    assert.ok(crew.crews.some((item) => item.id === "CREW-OFFSHORE-02"));

    const vessels = results.get("query_vessels");
    assert.ok(vessels.scope.linkedWorkOrderIds.includes("WO-20260823-017"));
    assert.ok(vessels.vessels.some((item) => item.id === "VESSEL-CTV-03"));
  });

  await t.test(
    "work-order updates are validated drafts and leave source state unchanged",
    async () => {
      const update = results.get("update_work_order");
      assert.equal(update.dryRun, true);
      assert.equal(update.persisted, false);
      assert.equal(update.workOrderId, "WO-20260823-017");
      assert.equal(update.before.status, "scheduled");
      assert.equal(update.draft.status, update.before.status);
      assert.notEqual(update.draft.assignedTeam, update.before.assignedTeam);

      const unchanged = await jsonRequest("POST", {
        tool: "query_work_orders",
        args: { workOrderId: "WO-20260823-017" },
        persist: false,
      });
      const source = unchanged.data.execution.result.data.workOrders[0];
      assert.equal(source.status, update.before.status);
      assert.equal(source.assignedTeam, update.before.assignedTeam);
      assert.equal(source.plannedStart, update.before.plannedStart);
      assert.equal(source.deadline, update.before.deadline);

      const invalidSchedule = await jsonRequest(
        "POST",
        {
          tool: "update_work_order",
          args: {
            workOrderId: "WO-20260823-017",
            plannedStart: "2026-08-14T18:00:00+08:00",
            deadline: "2026-08-14T17:00:00+08:00",
            dryRun: true,
          },
          persist: false,
        },
        422,
      );
      assert.equal(invalidSchedule.error.code, "INVALID_WORK_ORDER_SCHEDULE");
      assert.equal(invalidSchedule.data.execution.status, "failed");
      assert.equal(invalidSchedule.data.execution.result.dryRun, true);
    },
  );

  await t.test(
    "GET exposes the deterministic execution ledger without validation noise",
    async () => {
      const response = await jsonRequest("GET");
      assert.equal(response.ok, true);
      const recordedTools = [
        ...calls.map(([tool]) => tool),
        "query_work_orders",
        "update_work_order",
      ];
      assert.equal(response.meta.historyCount, recordedTools.length);
      assert.equal(response.data.executionHistory.length, recordedTools.length);
      assert.deepEqual(
        response.data.executionHistory.map((execution) => execution.request.tool),
        recordedTools,
      );
      assert.equal(
        new Set(response.data.executionHistory.map((execution) => execution.correlationId)).size,
        recordedTools.length,
      );
      assert.equal(
        response.data.executionHistory.filter((execution) => execution.status === "failed").length,
        1,
      );
      assert.equal(
        response.data.executionHistory.at(-1).result.error.code,
        "INVALID_WORK_ORDER_SCHEDULE",
      );
      assert.doesNotMatch(
        JSON.stringify(response.data),
        /chain.?of.?thought|\bcot\b|hidden reasoning/i,
      );
    },
  );
});
