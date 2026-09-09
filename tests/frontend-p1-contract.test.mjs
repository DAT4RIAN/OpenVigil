import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { agents } from "../lib/agent-data.ts";
import { turbines } from "../lib/farm-data.ts";
import { alarms, missions, workOrders } from "../lib/operations-data.ts";
import { canonicalDemoWorkflow } from "../lib/demo-workflow.ts";
import {
  deriveWorkflowKpis,
  overlayClientAgents,
  overlayClientAlarms,
  overlayClientMissions,
  overlayClientTurbines,
  overlayClientWorkOrders,
} from "../lib/client-workflow-overlays.ts";

const source = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("workflow overlay closes alarms and derives KPI and Agent state from one snapshot", () => {
  const completed = {
    ...canonicalDemoWorkflow,
    missionStatus: "completed",
    missionProgress: 100,
    workOrderStatus: "completed",
    turbineHealthScore: 92,
  };
  const displayTurbines = overlayClientTurbines(turbines, completed);
  const displayAlarms = overlayClientAlarms(alarms, completed);
  const displayMissions = overlayClientMissions(missions, completed);
  const displayAgents = overlayClientAgents(agents, completed);
  const kpis = deriveWorkflowKpis(displayTurbines, displayAlarms, displayMissions, displayAgents);

  assert.equal(displayTurbines.find((item) => item.id === "WT-023")?.healthScore, 92);
  assert.ok(
    displayAlarms
      .filter((item) => item.missionId === "MISSION-2026-0823")
      .every((item) => item.status === "resolved"),
  );
  assert.equal(
    displayMissions.find((item) => item.id === "MISSION-2026-0823")?.status,
    "completed",
  );
  assert.ok(
    displayAgents
      .filter((item) => item.currentMissionId === "MISSION-2026-0823")
      .every((item) => item.status === "idle" && item.currentTask === null),
  );
  assert.equal(
    kpis.activeMissionCount,
    displayMissions.filter((item) => item.status !== "completed").length,
  );
});

test("the reviewed alternative and its work order stay aligned in client projections", () => {
  const reviewed = {
    ...canonicalDemoWorkflow,
    decisionStatus: "approved",
    workOrderStatus: "scheduled",
    approval: {
      action: "approve",
      selectedAlternativeId: "ALT-0823-C",
      approver: "李明远",
      approverRole: "值班总工程师",
      timestamp: "2026-08-13T09:02:00+08:00",
      reason: "人工选择增强监测",
      comment: "批准方案 C",
    },
  };
  const workOrder = overlayClientWorkOrders(workOrders, reviewed).find(
    (item) => item.id === "WO-20260823-017",
  );

  assert.match(workOrder?.issue ?? "", /方案 C/);
  assert.match(workOrder?.description ?? "", /增强监测/);
  assert.match(workOrder?.tasks[1]?.title ?? "", /每 5 分钟/);
  assert.deepEqual(workOrder?.requiredTools, ["SCADA 远程诊断台", "CMS 在线监测"]);
});

test("command intent, scoped pages, honest controls and accessible drawers are source-locked", async () => {
  const [
    shell,
    missionsPage,
    workOrdersPage,
    scadaPage,
    decisionPage,
    windFarmPage,
    agentPage,
    agentTable,
    missionDetail,
    dashboard,
    knowledgePage,
    dataTable,
    dialogHook,
  ] = await Promise.all([
    source("components/layout/app-shell.tsx"),
    source("components/pages/mission-center-page.tsx"),
    source("components/pages/work-order-page.tsx"),
    source("components/pages/scada-page.tsx"),
    source("components/pages/decision-center-page.tsx"),
    source("components/pages/wind-farm-page.tsx"),
    source("components/pages/agent-control-page.tsx"),
    source("components/pages/agent-control-table.tsx"),
    source("components/pages/mission-detail-page.tsx"),
    source("components/pages/dashboard-page.tsx"),
    source("components/pages/knowledge-base-page.tsx"),
    source("components/data-display/data-table.tsx"),
    source("lib/use-accessible-dialog.ts"),
  ]);

  assert.match(shell, /Open Mission Center/);
  assert.match(shell, /Create Work Order · 只读受控入口/);
  assert.match(shell, /Start Diagnosis · 只读诊断入口/);
  assert.match(shell, /此命令不会创建工单/);
  assert.match(shell, /不会启动新 Agent 或写入诊断/);
  assert.match(shell, /intent=create/);
  assert.match(shell, /intent=diagnosis/);
  assert.match(workOrdersPage, /parameters\.get\("intent"\) === "create"/);
  assert.match(workOrdersPage, /不会假创建工单/);
  assert.match(missionsPage, /\.get\("turbineId"\)/);
  assert.match(missionsPage, /不会假启动 Agent 流程/);
  assert.match(scadaPage, /requestFullscreen/);
  assert.match(decisionPage, /setShowAllEvidence/);
  assert.match(windFarmPage, /更多筛选维度尚未接入/);
  assert.match(windFarmPage, /当前筛选下没有可绘制的拓扑节点/);
  assert.match(agentPage, /scrollIntoView/);
  assert.match(agentPage, /toolTest\.mutate/);
  assert.match(agentPage, /<AgentControlTable/);
  assert.match(agentTable, /<DataTable/);
  assert.match(agentTable, /csvExport=/);
  assert.match(agentTable, /bulkActions=/);
  assert.match(missionDetail, /encodeURIComponent\(agent\.id\)/);
  assert.doesNotMatch(missionDetail, /当前版本暂无更多操作/);
  assert.match(dashboard, /href="\/wind-farms"/);
  assert.match(shell, /useAccessibleDialog<HTMLDivElement>\(onClose, open\)/);
  assert.match(knowledgePage, /useAccessibleDialog<HTMLElement>\(onClose\)/);
  assert.match(dataTable, /cameFromInteractiveChild/);
  assert.match(dataTable, /closest\(/);
  assert.match(dataTable, /\[data-row-activation-ignore\]/);
  assert.match(dialogHook, /event\.key === "Escape"/);
  assert.match(dialogHook, /event\.key !== "Tab"/);
  assert.match(dialogHook, /restoreTarget\?\.focus/);
});

test("all five drawers use the shared accessible dialog", async () => {
  const drawerFiles = [
    "components/pages/wind-farm-page.tsx",
    "components/pages/alarm-center-page.tsx",
    "components/pages/work-order-page.tsx",
    "components/pages/agent-control-page.tsx",
    "components/pages/knowledge-base-page.tsx",
  ];
  for (const file of drawerFiles) {
    assert.match(await source(file), /useAccessibleDialog/);
  }
});
