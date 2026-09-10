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
    Promise.all([
      source("components/pages/work-order-page.tsx"),
      source("components/pages/work-order-drawer.tsx"),
      source("components/pages/work-order-support.tsx"),
    ]).then((parts) => parts.join("\n")),
    source("components/pages/scada-page.tsx"),
    source("components/pages/decision-center-page.tsx"),
    source("components/pages/wind-farm-page.tsx"),
    Promise.all([
      source("components/pages/agent-control-page.tsx"),
      source("components/pages/agent-control-drawer.tsx"),
      source("components/pages/agent-control-support.ts"),
    ]).then((parts) => parts.join("\n")),
    source("components/pages/agent-control-table.tsx"),
    Promise.all([
      source("components/pages/mission-detail-featured.tsx"),
      source("components/pages/mission-detail-generic.tsx"),
      source("components/pages/mission-detail-production.tsx"),
    ]).then((parts) => parts.join("\n")),
    Promise.all([
      source("components/pages/dashboard-demo-page.tsx"),
      source("components/pages/dashboard-production-page.tsx"),
    ]).then((parts) => parts.join("\n")),
    source("components/pages/knowledge-base-page.tsx"),
    source("components/data-display/data-table.tsx"),
    source("lib/use-accessible-dialog.ts"),
  ]);

  assert.match(shell, /打开 Mission 中心/);
  assert.match(shell, /创建工单 · 只读受控入口/);
  assert.match(shell, /启动诊断 · 只读诊断入口/);
  assert.match(shell, /此命令不会创建工单/);
  assert.match(shell, /不会启动新 Agent 或写入诊断/);
  assert.match(shell, /intent=create/);
  assert.match(shell, /intent=diagnosis/);
  assert.match(workOrdersPage, /parameters\.get\("intent"\) === "create"/);
  assert.match(workOrdersPage, /crypto\.subtle\.digest\("SHA-256"/);
  assert.match(workOrdersPage, /\/artifacts\/presign/);
  assert.match(workOrdersPage, /grant\.required_headers/);
  assert.match(workOrdersPage, /MAX_FIELD_ARTIFACT_BYTES/);
  assert.match(workOrdersPage, /onProductionTaskCompleted/);
  assert.match(workOrdersPage, /不会假创建工单/);
  assert.match(missionsPage, /\.get\("turbineId"\)/);
  assert.match(missionsPage, /不会假启动 Agent 流程/);
  assert.match(scadaPage, /requestFullscreen/);
  assert.match(decisionPage, /setShowAllEvidence/);
  assert.match(decisionPage, /\/api\/backend\/missions\//);
  assert.match(decisionPage, /expected_revision/);
  assert.match(decisionPage, /selected_alternative_id/);
  assert.match(decisionPage, /productionMode/);
  assert.match(windFarmPage, /aria-label="风场高级筛选"/);
  assert.match(windFarmPage, /仅已配置坐标/);
  assert.match(windFarmPage, /清除高级筛选/);
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
    "components/pages/alarm-center-drawer.tsx",
    "components/pages/work-order-drawer.tsx",
    "components/pages/agent-control-drawer.tsx",
    "components/pages/knowledge-base-page.tsx",
  ];
  for (const file of drawerFiles) {
    assert.match(await source(file), /useAccessibleDialog/);
  }
});

test("production branches never render fixture drawer, approval, summary, or diagnosis data", async () => {
  const [alarmPage, decisionPage, missionPage, diagnosisPage] = await Promise.all([
    Promise.all([
      source("components/pages/alarm-center-page.tsx"),
      source("components/pages/alarm-center-drawer.tsx"),
      source("components/pages/alarm-center-support.tsx"),
    ]).then((parts) => parts.join("\n")),
    source("components/pages/decision-center-page.tsx"),
    source("components/pages/mission-center-page.tsx"),
    source("components/pages/diagnosis-center-page.tsx"),
  ]);

  // F1: 告警抽屉的特色卡与 fixture 关联数据只允许出现在 demo 分支。
  assert.match(alarmPage, /const featured = !production &&/);
  assert.match(alarmPage, /const relatedEvidence = production\s*\?\s*\[\]/);
  assert.match(alarmPage, /const similarCases = production\s*\?\s*\[\]/);
  assert.match(alarmPage, /const maintenanceRecords = production\s*\?\s*\[\]/);
  assert.match(alarmPage, /const referencedKnowledge = production\s*\?\s*\[\]/);
  // 生产模式接线权威后端：告警详情证据、Mission 关联、相似案例、工单与知识文档。
  assert.match(alarmPage, /\/api\/backend\/alarms\/\$\{encodeURIComponent\(alarm\.id\)\}/);
  assert.match(alarmPage, /\/api\/backend\/knowledge\/cases\?mission_id=/);
  assert.match(alarmPage, /\/api\/backend\/work-orders\?turbine_id=/);
  assert.match(alarmPage, /\/api\/backend\/knowledge\/documents\?q=/);
  assert.match(alarmPage, /enabled: production/);
  // 失败关闭与显式空态，不静默回落到 fixture。
  assert.match(alarmPage, /已失败关闭，不回退演示数据/);
  assert.match(alarmPage, /不会展示演示诊断结论/);

  // F2: 生产审批意见必须显式输入，演示文案不得进入生产 POST。
  assert.match(decisionPage, /productionMode \? "" : "同意执行方案 B/);
  assert.match(decisionPage, /不会代入演示文案/);
  assert.match(decisionPage, /productionMode && comment\.trim\(\)\.length < 3/);
  assert.match(decisionPage, /reason: comment\.trim\(\)/);

  // F3: Mission 汇总区在 production 下统计真实 Mission 数据，不读 fixture agents。
  assert.match(missionPage, /const participatingAgentCount =/);
  assert.doesNotMatch(
    missionPage,
    /<strong>\{agents\.filter\(\(agent\) => agent\.currentMissionId\)\.length\}<\/strong>/,
  );
  assert.match(missionPage, /暂无已闭环 Mission，无法计算/);
  assert.match(missionPage, /基于 \$\{resolutionMinutes\.length\} 个已闭环 Mission 计算/);

  // F4: 诊断中心 production 不硬链 fixture Mission、不携带 fixture 模型声明。
  assert.match(diagnosisPage, /查看 \{selected\.turbineId\} Mission/);
  assert.match(diagnosisPage, /model: isProduction/);
  assert.match(diagnosisPage, /正在读取生产诊断模型元数据/);
  assert.doesNotMatch(
    diagnosisPage,
    /actions=\{\s*<Link className="button button--secondary button--md" href="\/missions\/MISSION-2026-0823">/,
  );
});

test("production knowledge and report routes do not fall back to demo scope or paginated reports", async () => {
  const [knowledgeAssistant, reportDetail, reportExport, productionRuntime] = await Promise.all([
    source("app/api/knowledge-assistant/route.ts"),
    source("app/api/reports/[id]/route.ts"),
    source("app/api/reports/[id]/export/route.ts"),
    source("lib/production-runtime.ts"),
  ]);

  assert.match(knowledgeAssistant, /const productionMode = getProductionBackendConfig\(\)\.mode/);
  assert.match(knowledgeAssistant, /productionMode \? null : featuredMission\.turbineId/);
  assert.match(knowledgeAssistant, /productionMode \? null : featuredMission\.id/);
  assert.match(knowledgeAssistant, /if \(productionMode\)/);
  assert.match(reportDetail, /"\/api\/v1\/reports\/" \+ encodeURIComponent\(id\)/);
  assert.match(reportExport, /"\/api\/v1\/reports\/" \+ encodeURIComponent\(id\)/);
  assert.doesNotMatch(reportExport, /new URL\("\/api\/reports",/);
  assert.match(productionRuntime, /reports\(\?:\\\/\[\^\/\]\+\)\?/);
});
