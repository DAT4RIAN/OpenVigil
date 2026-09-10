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
  assert.match(html, /运营指挥中心/);
  assert.match(html, /WT-023/);
  assert.match(html, /MISSION-2026-0823/);
  assert.doesNotMatch(html, /codex-preview/i);
  assert.doesNotMatch(html, /react-loading-skeleton|Your site is taking shape|Building your site/i);
});

test("agent roster covers the three-layer specification and only declares catalog tools", async () => {
  const [agentResponse, toolResponse] = await Promise.all([
    fetchJson("/api/agents"),
    fetchJson("/api/agent-tools?limit=1"),
  ]);
  const expectedByLayer = {
    decision: [
      "Operations Coordinator Agent",
      "SCADA Analysis Agent",
      "Vibration Diagnosis Agent",
      "Structural Health Agent",
      "Electrical Diagnosis Agent",
      "Meteorological Risk Agent",
      "Failure Diagnosis Agent",
      "Predictive Maintenance Agent",
    ],
    review: [
      "Safety Review Agent",
      "Engineering Review Agent",
      "Economic Review Agent",
      "Compliance Agent",
      "Resource Review Agent",
    ],
    execution: [
      "Work Order Agent",
      "Crew Scheduling Agent",
      "Spare Parts Agent",
      "Vessel Scheduling Agent",
      "Maintenance Execution Agent",
      "SCADA Control Agent",
      "Report Agent",
      "Knowledge Agent",
    ],
  };
  const agents = agentResponse.data;
  const agentNames = new Set(agents.map((agent) => agent.name));
  const catalogNames = new Set(toolResponse.data.catalog.map((tool) => tool.name));

  assert.equal(agentResponse.meta.count, 22, "the full 21-role matrix plus one extra role is kept");
  assert.equal(new Set(agents.map((agent) => agent.id)).size, agents.length);
  assert.equal(agentNames.size, agents.length);
  assert.ok(agentNames.has("Maintenance Strategy Agent"), "the existing extra role is preserved");

  for (const [layer, requiredNames] of Object.entries(expectedByLayer)) {
    for (const name of requiredNames) {
      const agent = agents.find((candidate) => candidate.name === name);
      assert.ok(agent, `${name} is missing from the agent roster`);
      assert.equal(agent.layer, layer, `${name} is assigned to the wrong layer`);
    }
  }

  for (const agent of agents) {
    assert.ok(agent.role.length > 0, `${agent.name} is missing a role`);
    assert.ok(agent.description.length > 0, `${agent.name} is missing a description`);
    assert.ok(agent.skills.length > 0, `${agent.name} is missing skills`);
    assert.ok(agent.tools.length > 0, `${agent.name} is missing tools`);
    assert.ok(agent.knowledgeSourceIds.length > 0, `${agent.name} is missing knowledge sources`);
    assert.ok(agent.queueDepth >= 0, `${agent.name} has an invalid queue depth`);
    if (agent.status !== "idle" && agent.status !== "offline") {
      assert.ok(agent.currentTask, `${agent.name} must expose its current task`);
    }
    for (const tool of agent.tools) {
      assert.ok(catalogNames.has(tool), `${agent.name} declares unknown tool ${tool}`);
    }
  }
});

test("workflow-backed collection APIs share one envelope and one WT-023 assignment graph", async () => {
  const [missionResponse, decisionResponse, evidenceResponse, alarmResponse, agentResponse] =
    await Promise.all([
      fetchJson("/api/missions"),
      fetchJson("/api/decisions"),
      fetchJson("/api/evidence"),
      fetchJson("/api/alarms"),
      fetchJson("/api/agents"),
    ]);

  for (const response of [
    missionResponse,
    decisionResponse,
    evidenceResponse,
    alarmResponse,
    agentResponse,
  ]) {
    assert.equal(response.meta.count, response.data.length);
    assert.equal(response.meta.total, response.data.length);
    assert.equal(response.meta.workflowPersistence, "ephemeral");
    assert.equal(response.meta.workflowRevision, 0);
    assert.equal(response.meta.snapshotAt, missionResponse.meta.snapshotAt);
  }

  const mission = missionResponse.data.find(({ id }) => id === "MISSION-2026-0823");
  const decision = decisionResponse.data.find(({ id }) => id === "DECISION-2026-0823");
  const relatedEvidence = evidenceResponse.data.filter(({ missionId }) => missionId === mission.id);
  const relatedAlarms = alarmResponse.data.filter(({ missionId }) => missionId === mission.id);
  const assignedAgents = agentResponse.data.filter(
    ({ currentMissionId }) => currentMissionId === mission.id,
  );

  assert.equal(mission.status, "under-review");
  assert.match(mission.summary, /等待人工审批/);
  assert.match(mission.nextAction, /人工审批/);
  assert.equal(decision.status, "under-review");
  assert.deepEqual(decision.approval, {
    required: true,
    action: null,
    selectedAlternativeId: null,
    approver: null,
    approverRole: null,
    timestamp: null,
    reason: null,
    comment: null,
  });
  assert.deepEqual(new Set(relatedEvidence.map(({ id }) => id)), new Set(decision.evidenceIds));
  assert.deepEqual(new Set(relatedAlarms.map(({ id }) => id)), new Set(mission.alarmIds));
  assert.ok(relatedAlarms.every(({ status }) => status !== "resolved"));

  assert.deepEqual(
    new Set(assignedAgents.map(({ id }) => id)),
    new Set(mission.agentIds),
    "the featured mission and agent roster must declare the same active participants",
  );
  assert.ok(mission.agentIds.includes(mission.leadAgentId));
  assert.equal(
    assignedAgents.find(({ id }) => id === mission.leadAgentId)?.currentMissionId,
    mission.id,
    "the featured lead must be actively assigned to the featured mission",
  );
  assert.ok(
    assignedAgents.every(
      ({ layer, status, currentTask }) =>
        currentTask && (layer === "review" ? status === "reviewing" : status !== "working"),
    ),
    "pre-approval roles must expose review or waiting work instead of execution work",
  );

  const missionsById = new Map(missionResponse.data.map((item) => [item.id, item]));
  for (const agent of agentResponse.data) {
    if (!agent.currentMissionId) continue;
    const currentMission = missionsById.get(agent.currentMissionId);
    assert.ok(currentMission, `${agent.id} has an unknown current mission`);
    assert.ok(
      currentMission.agentIds.includes(agent.id),
      `${agent.id} is not declared by ${agent.currentMissionId}`,
    );
  }
  for (const item of missionResponse.data) {
    assert.ok(item.agentIds.includes(item.leadAgentId), `${item.id} omits its lead agent`);
  }
});

test("mock APIs distinguish live and archive fixture counts", async () => {
  const [
    health,
    farms,
    turbines,
    alarms,
    archivedAlarms,
    missions,
    agents,
    workOrders,
    historicalWorkOrders,
    failureCases,
  ] = await Promise.all([
    fetchJson("/api/health"),
    fetchJson("/api/wind-farms"),
    fetchJson("/api/turbines"),
    fetchJson("/api/alarms"),
    fetchJson("/api/alarms?scope=archive"),
    fetchJson("/api/missions"),
    fetchJson("/api/agents"),
    fetchJson("/api/work-orders"),
    fetchJson("/api/work-orders?scope=archive"),
    fetchJson("/api/failure-cases"),
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
  assert.equal(
    alarms.data.filter((alarm) => alarm.status !== "resolved").length,
    farms.data[0].activeAlarmCount,
  );
  assert.equal(farms.data[0].activeAlarmCount, 17);
  assert.equal(alarms.meta.scope, "live");
  assert.equal(workOrders.meta.scope, "live");
  assert.equal(archivedAlarms.meta.scope, "archive");
  assert.equal(historicalWorkOrders.meta.scope, "archive");
  assert.equal(failureCases.meta.scope, "archive");

  assert.equal(health.counts.live.windFarms, farms.meta.count);
  assert.equal(health.counts.live.turbines, turbines.meta.count);
  assert.equal(health.counts.live.scadaSeries, 17);
  assert.equal(health.counts.live.scadaPoints, 1_649);
  assert.equal(health.counts.live.alarms, alarms.meta.count);
  assert.equal(health.counts.live.unresolvedAlarms, 17);
  assert.equal(health.counts.live.missions, missions.meta.count);
  assert.equal(missions.meta.count, 12);
  assert.equal(
    missions.data.filter((mission) => mission.status !== "completed").length,
    10,
    "the command center must expose ten active missions",
  );
  assert.equal(health.counts.live.activeMissions, 10);
  assert.equal(health.counts.live.agentTools, 17);
  assert.deepEqual(
    {
      spareParts: health.counts.live.spareParts,
      maintenanceCrews: health.counts.live.maintenanceCrews,
      serviceVessels: health.counts.live.serviceVessels,
      maintenanceTools: health.counts.live.maintenanceTools,
    },
    { spareParts: 7, maintenanceCrews: 4, serviceVessels: 3, maintenanceTools: 6 },
  );
  assert.equal(health.counts.live.agents, agents.meta.count);
  assert.equal(health.counts.live.workOrders, workOrders.meta.count);

  assert.equal(archivedAlarms.meta.count, 100);
  assert.equal(historicalWorkOrders.meta.count, 30);
  assert.equal(failureCases.meta.count, 20);
  assert.deepEqual(health.counts.archive, {
    scadaMeasurements: 131_072,
    alarms: 100,
    historicalWorkOrders: 30,
    failureCases: 20,
  });
  assert.deepEqual(health.counts.dataset, {
    turbines: 64,
    scadaMeasurements: 131_072,
    alarms: 100,
    liveAlarms: alarms.meta.count,
    workOrders: workOrders.meta.count + historicalWorkOrders.meta.count,
    liveWorkOrders: workOrders.meta.count,
    historicalWorkOrders: 30,
    failureCases: 20,
  });

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

  const historicalWorkOrderIds = new Set(
    historicalWorkOrders.data.map((workOrder) => workOrder.id),
  );
  for (const alarm of archivedAlarms.data) {
    assert.ok(turbineIds.has(alarm.turbineId), `${alarm.id} has an unknown turbine`);
    if (alarm.missionId) {
      assert.ok(missionIds.has(alarm.missionId), `${alarm.id} has an unknown mission`);
    }
  }
  for (const workOrder of historicalWorkOrders.data) {
    assert.ok(turbineIds.has(workOrder.turbineId), `${workOrder.id} has an unknown turbine`);
  }
  for (const failureCase of failureCases.data) {
    assert.ok(turbineIds.has(failureCase.turbineId), `${failureCase.id} has an unknown turbine`);
    assert.ok(
      historicalWorkOrderIds.has(failureCase.relatedWorkOrderId),
      `${failureCase.id} has an unknown work order`,
    );
  }

  const badAlarmScope = await fetchJson("/api/alarms?scope=everything", 400);
  assert.equal(badAlarmScope.error.code, "INVALID_SCOPE");
  const badWorkOrderScope = await fetchJson("/api/work-orders?scope=everything", 400);
  assert.equal(badWorkOrderScope.error.code, "INVALID_SCOPE");
});

test("SCADA archive pagination and filters are exact and deterministic", async () => {
  const [first, repeated, next, turbine, metric, combined] = await Promise.all([
    fetchJson("/api/scada-measurements?offset=4095&limit=5"),
    fetchJson("/api/scada-measurements?offset=4095&limit=5"),
    fetchJson("/api/scada-measurements?offset=4100&limit=5"),
    fetchJson("/api/scada-measurements?turbineId=wt-023&limit=1000"),
    fetchJson("/api/scada-measurements?metric=main-bearing-temperature&limit=1000"),
    fetchJson(
      "/api/scada-measurements?turbineId=WT-023&metric=main-bearing-temperature&limit=1000",
    ),
  ]);

  assert.equal(first.meta.total, 131_072);
  assert.equal(first.meta.offset, 4_095);
  assert.equal(first.meta.limit, 5);
  assert.equal(first.meta.count, 5);
  assert.deepEqual(repeated, first);
  assert.equal(
    first.data.some((measurement) =>
      next.data.some((candidate) => candidate.id === measurement.id),
    ),
    false,
  );

  assert.equal(turbine.meta.total, 2_048);
  assert.equal(turbine.meta.turbineId, "WT-023");
  assert.ok(turbine.data.every((measurement) => measurement.turbineId === "WT-023"));

  assert.equal(metric.meta.total, 8_192);
  assert.equal(metric.meta.metric, "main-bearing-temperature");
  assert.ok(metric.data.every((measurement) => measurement.metric === "main-bearing-temperature"));

  assert.equal(combined.meta.total, 128);
  assert.equal(combined.meta.count, 128);
  assert.ok(
    combined.data.every(
      (measurement) =>
        measurement.turbineId === "WT-023" && measurement.metric === "main-bearing-temperature",
    ),
  );

  const invalidOffset = await fetchJson("/api/scada-measurements?offset=-1", 400);
  assert.equal(invalidOffset.error.code, "INVALID_PAGINATION");
  const invalidLimit = await fetchJson("/api/scada-measurements?limit=1001", 400);
  assert.equal(invalidLimit.error.code, "INVALID_PAGINATION");
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

  const mission = missions.data.find((candidate) => candidate.id === "MISSION-2026-0823");
  assert.ok(mission, "the featured WT-023 mission must exist");
  assert.equal(mission.turbineId, "WT-023");
  assert.ok(mission.alarmIds.length >= 1);
  assert.ok(mission.decisionId);
  assert.ok(mission.workOrderId);

  const relatedAlarms = alarms.data.filter((alarm) => alarm.missionId === mission.id);
  assert.deepEqual(new Set(relatedAlarms.map((alarm) => alarm.id)), new Set(mission.alarmIds));
  assert.ok(relatedAlarms.every((alarm) => alarm.turbineId === "WT-023"));

  const workOrder = workOrders.data.find((candidate) => candidate.relatedMissionId === mission.id);
  assert.ok(workOrder, "the featured mission must generate a work order");
  assert.equal(workOrder.id, mission.workOrderId);
  assert.equal(workOrder.turbineId, "WT-023");
  assert.equal(workOrder.decisionId, mission.decisionId);

  assert.ok(detail.relationships.missionIds.includes(mission.id));
  assert.ok(detail.relationships.workOrderIds.includes(workOrder.id));
  assert.deepEqual(new Set(detail.relationships.alarmIds), new Set(mission.alarmIds));

  const missing = await fetchJson("/api/turbines/WT-999", 404);
  assert.equal(missing.error.code, "TURBINE_NOT_FOUND");
});

test("agent activity endpoint is a deterministic finite SSE replay", async () => {
  const [health, response] = await Promise.all([
    fetchJson("/api/health"),
    fetchRoute("/api/agent-events", { accept: "text/event-stream" }),
  ]);

  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/event-stream\b/i);

  const body = await response.text();
  assert.match(body, /^event: snapshot/m);
  assert.match(body, /event: agent-activity/);
  assert.match(body, /"missionId":"MISSION-2026-0823"/);
  assert.match(body, /event: complete/);
  assert.equal(
    (body.match(/^event: agent-activity$/gm) ?? []).length,
    health.counts.live.agentEvents,
  );
});
