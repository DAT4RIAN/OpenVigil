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

test("deterministic Agent Tool API validates, executes, links, and records every P0 tool", async (t) => {
  await t.test("catalog starts with an empty deterministic runtime history", async () => {
    const response = await jsonRequest("GET");
    assert.equal(response.ok, true);
    assert.equal(response.error, null);
    assert.equal(response.meta.deterministic, true);
    assert.equal(response.meta.persisted, false);
    assert.equal(response.data.catalog.length, 11);
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
    ]);
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
  ];

  const results = new Map();

  await t.test(
    "all eleven tools execute against fixtures with complete observability records",
    async () => {
      for (const [tool, args] of calls) {
        const response = await jsonRequest("POST", { tool, args });
        assert.equal(response.ok, true, `${tool} should succeed`);
        assert.equal(response.error, null);
        assert.equal(response.meta.deterministic, true);
        assert.equal(response.meta.persisted, false);

        const execution = response.data.execution;
        assert.equal(execution.request.tool, tool);
        assert.equal(execution.status, "succeeded");
        assert.equal(execution.result.ok, true);
        assert.equal(execution.deterministic, true);
        assert.match(
          execution.correlationId,
          new RegExp(`^WOPS-${tool.toUpperCase()}-[0-9a-f]{8}-\\d{4}$`),
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

  await t.test(
    "GET exposes the deterministic execution ledger without validation noise",
    async () => {
      const response = await jsonRequest("GET");
      assert.equal(response.ok, true);
      assert.equal(response.meta.historyCount, calls.length);
      assert.equal(response.data.executionHistory.length, calls.length);
      assert.deepEqual(
        response.data.executionHistory.map((execution) => execution.request.tool),
        calls.map(([tool]) => tool),
      );
      assert.equal(
        new Set(response.data.executionHistory.map((execution) => execution.correlationId)).size,
        calls.length,
      );
      assert.ok(
        response.data.executionHistory.every((execution) => execution.status === "succeeded"),
      );
    },
  );
});
