import assert from "node:assert/strict";
import test from "node:test";

const workerUrl = new URL("../dist/server/index.js", import.meta.url);
workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
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

function fetchRoute(path, headers = {}) {
  return worker.fetch(
    new Request(new URL(path, "http://localhost"), { headers }),
    environment,
    context,
  );
}

async function fetchJson(path, expectedStatus = 200) {
  const response = await fetchRoute(path, { accept: "application/json" });
  assert.equal(response.status, expectedStatus, `${path} returned ${response.status}`);
  assert.match(response.headers.get("content-type") ?? "", /^application\/json\b/i);
  return response.json();
}

test("server-renders the WindOps command center instead of the starter", async () => {
  const response = await fetchRoute("/", { accept: "text/html" });

  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /WindOps/);
  assert.match(html, /Operations Command Center/);
  assert.match(html, /WT-023/);
  assert.match(html, /MISSION-2026-0823/);
  assert.doesNotMatch(html, /codex-preview/i);
  assert.doesNotMatch(html, /react-loading-skeleton|Your site is taking shape|Building your site/i);
});

test("mock APIs expose complete, referentially valid fixture counts", async () => {
  const [health, farms, turbines, alarms, missions, agents, workOrders] =
    await Promise.all([
      fetchJson("/api/health"),
      fetchJson("/api/wind-farms"),
      fetchJson("/api/turbines"),
      fetchJson("/api/alarms"),
      fetchJson("/api/missions"),
      fetchJson("/api/agents"),
      fetchJson("/api/work-orders"),
    ]);

  assert.equal(health.status, "healthy");
  assert.equal(health.deterministic, true);
  assert.equal(health.readOnly, true);
  assert.deepEqual(health.integrity, {
    valid: true,
    errorCount: 0,
    errors: [],
  });

  assert.equal(farms.meta.count, 1);
  assert.equal(turbines.meta.count, 64);
  assert.equal(farms.data[0].turbineCount, turbines.meta.count);
  assert.equal(health.counts.windFarms, farms.meta.count);
  assert.equal(health.counts.turbines, turbines.meta.count);
  assert.equal(health.counts.alarms, alarms.meta.count);
  assert.equal(health.counts.missions, missions.meta.count);
  assert.equal(health.counts.agents, agents.meta.count);
  assert.equal(health.counts.workOrders, workOrders.meta.count);

  const turbineIds = new Set(turbines.data.map((turbine) => turbine.id));
  const missionIds = new Set(missions.data.map((mission) => mission.id));
  const agentIds = new Set(agents.data.map((agent) => agent.id));

  for (const alarm of alarms.data) {
    assert.ok(turbineIds.has(alarm.turbineId), `${alarm.id} has an unknown turbine`);
    if (alarm.missionId) {
      assert.ok(missionIds.has(alarm.missionId), `${alarm.id} has an unknown mission`);
    }
  }

  for (const mission of missions.data) {
    assert.ok(turbineIds.has(mission.turbineId), `${mission.id} has an unknown turbine`);
    assert.ok(agentIds.has(mission.leadAgentId), `${mission.id} has an unknown lead agent`);
  }

  for (const workOrder of workOrders.data) {
    assert.ok(turbineIds.has(workOrder.turbineId), `${workOrder.id} has an unknown turbine`);
    if (workOrder.relatedMissionId) {
      assert.ok(
        missionIds.has(workOrder.relatedMissionId),
        `${workOrder.id} has an unknown mission`,
      );
    }
  }
});

test("WT-023 APIs preserve the alarm-to-mission-to-work-order closed loop", async () => {
  const [detail, scada, alarms, missions, workOrders] = await Promise.all([
    fetchJson("/api/turbines/wt-023"),
    fetchJson("/api/turbines/WT-023/scada"),
    fetchJson("/api/alarms"),
    fetchJson("/api/missions"),
    fetchJson("/api/work-orders"),
  ]);

  assert.equal(detail.data.id, "WT-023");
  assert.equal(scada.meta.turbineId, "WT-023");
  assert.ok(scada.meta.count >= 1);
  assert.ok(scada.data.every((series) => series.turbineId === "WT-023"));

  const mission = missions.data.find(
    (candidate) => candidate.id === "MISSION-2026-0823",
  );
  assert.ok(mission, "the featured WT-023 mission must exist");
  assert.equal(mission.turbineId, "WT-023");
  assert.ok(mission.alarmIds.length >= 1);
  assert.ok(mission.decisionId);
  assert.ok(mission.workOrderId);

  const relatedAlarms = alarms.data.filter(
    (alarm) => alarm.missionId === mission.id,
  );
  assert.deepEqual(
    new Set(relatedAlarms.map((alarm) => alarm.id)),
    new Set(mission.alarmIds),
  );
  assert.ok(relatedAlarms.every((alarm) => alarm.turbineId === "WT-023"));

  const workOrder = workOrders.data.find(
    (candidate) => candidate.relatedMissionId === mission.id,
  );
  assert.ok(workOrder, "the featured mission must generate a work order");
  assert.equal(workOrder.id, mission.workOrderId);
  assert.equal(workOrder.turbineId, "WT-023");
  assert.equal(workOrder.decisionId, mission.decisionId);

  assert.ok(detail.relationships.missionIds.includes(mission.id));
  assert.ok(detail.relationships.workOrderIds.includes(workOrder.id));
  assert.deepEqual(
    new Set(detail.relationships.alarmIds),
    new Set(mission.alarmIds),
  );

  const missing = await fetchJson("/api/turbines/WT-999", 404);
  assert.equal(missing.error.code, "TURBINE_NOT_FOUND");
});

test("agent activity endpoint is a deterministic finite SSE replay", async () => {
  const [health, response] = await Promise.all([
    fetchJson("/api/health"),
    fetchRoute("/api/agent-events", { accept: "text/event-stream" }),
  ]);

  assert.equal(response.status, 200);
  assert.match(
    response.headers.get("content-type") ?? "",
    /^text\/event-stream\b/i,
  );

  const body = await response.text();
  assert.match(body, /^event: snapshot/m);
  assert.match(body, /event: agent-activity/);
  assert.match(body, /"missionId":"MISSION-2026-0823"/);
  assert.match(body, /event: complete/);
  assert.equal(
    (body.match(/^event: agent-activity$/gm) ?? []).length,
    health.counts.agentEvents,
  );
});
