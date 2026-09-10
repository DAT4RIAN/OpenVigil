import {
  expect,
  test,
  type Browser,
  type BrowserContext,
  type Page,
  type Route,
} from "@playwright/test";

const baseURL = "http://127.0.0.1:4179";

function identityHeaders() {
  return {
    "oai-authenticated-user-id": "user-manager",
    "oai-authenticated-user-email": "user-manager@example.com",
  };
}

async function productionPage(browser: Browser): Promise<{
  context: BrowserContext;
  page: Page;
}> {
  const context = await browser.newContext({
    baseURL,
    viewport: { width: 1440, height: 900 },
    extraHTTPHeaders: identityHeaders(),
  });
  return { context, page: await context.newPage() };
}

async function fulfillJson(
  route: Route,
  body: unknown,
  status = 200,
  correlationId = "query-state-e2e",
) {
  await route.fulfill({
    status,
    contentType: "application/json",
    headers: { "x-correlation-id": correlationId },
    body: JSON.stringify(body),
  });
}

async function installSharedRoutes(page: Page) {
  await page.route("**/api/runtime", (route) =>
    fulfillJson(route, {
      data: {
        runtimeMode: "production",
        backendAuthentication: "delegation",
        productionReady: true,
        fixtureFallbackAllowed: false,
        backend: { reachable: true },
      },
      error: null,
      meta: { readOnly: true, secretsRedacted: true },
    }),
  );
  await page.route("**/api/alarms", (route) =>
    fulfillJson(route, { data: [], meta: { count: 0 } }),
  );
}

const mission = (updatedAt: string) => ({
  id: "MISSION-STATE-001",
  turbineId: "WT-901",
  title: "状态矩阵 Mission",
  summary: "用于验证生产读取状态不会伪造成功。",
  severity: "high",
  status: "investigating",
  progressPercent: 42,
  leadAgentId: "diagnosis-agent",
  agentIds: ["diagnosis-agent"],
  alarmIds: [],
  evidenceIds: [],
  diagnosis: null,
  confidencePercent: null,
  decisionId: null,
  workOrderId: null,
  nextAction: "等待权威证据",
  createdAt: "2026-09-04T07:00:00.000Z",
  updatedAt,
  targetResolutionAt: "2026-09-05T07:00:00.000Z",
});

const decision = (updatedAt: string) => ({
  id: "DECISION-STATE-001",
  missionId: "MISSION-STATE-001",
  missionRevision: 7,
  turbineId: "WT-901",
  incident: "状态矩阵决策事件",
  diagnosis: "主轴承振动趋势需要人工复核后才能授权现场处置。",
  confidencePercent: 86,
  status: "under-review",
  risk: "high",
  evidenceIds: ["EVIDENCE-STATE-001"],
  alternatives: [
    {
      id: "ALT-STATE-001",
      label: "方案 A",
      title: "受控降载并安排检查",
      description: "先限制负荷，再于合适窗口执行主轴承检查。",
      safetyRisk: "low",
      deteriorationRiskPercent: 12,
      estimatedCostCny: 68000,
      estimatedDowntimeHours: 4,
      estimatedEnergyLossMWh: 9.2,
      weatherWindowId: null,
      requiredResources: ["海维测试组", "振动分析仪"],
      recommended: true,
      rationale: "兼顾安全边界、停机窗口和恶化风险。",
    },
  ],
  recommendedAlternativeId: "ALT-STATE-001",
  recommendedAction: "受控降载并安排检查",
  weatherWindowId: null,
  requiredResources: ["海维测试组", "振动分析仪"],
  approval: {
    required: true,
    action: null,
    selectedAlternativeId: null,
    approver: null,
    approverRole: null,
    timestamp: null,
    reason: null,
    comment: null,
  },
  createdAt: "2026-09-04T07:00:00.000Z",
  updatedAt,
});

const workOrder = (updatedAt: string) => ({
  id: "WO-STATE-001",
  turbineId: "WT-901",
  issue: "状态矩阵主轴承检查",
  description: "验证工单台账读取状态。",
  priority: "high",
  status: "scheduled",
  assignedTeam: "海维测试组",
  createdByAgentId: "maintenance-agent",
  relatedMissionId: "MISSION-STATE-001",
  decisionId: "DECISION-STATE-001",
  plannedStart: "2026-09-05T08:00:00.000Z",
  deadline: "2026-09-05T12:00:00.000Z",
  estimatedDurationHours: 4,
  riskLevel: "high",
  tasks: [
    {
      id: "TASK-STATE-001",
      sequence: 1,
      title: "检查主轴承",
      completed: false,
      completionNote: null,
    },
  ],
  ppeRequirements: ["安全帽"],
  requiredTools: ["振动分析仪"],
  spareParts: [],
  safetyProcedures: ["执行上锁挂牌"],
  eam: null,
  createdAt: "2026-09-04T07:00:00.000Z",
  updatedAt,
});

const assessment = (assessedAt: string) => ({
  id: "ASSESSMENT-STATE-001",
  turbineId: "WT-901",
  healthScore: 68,
  state: "degraded",
  trend: "declining",
  riskLevel: "high",
  anomalyScore: 0.78,
  primaryFinding: "状态矩阵主轴承振动上升",
  assessedAt,
  component: "主轴承",
  componentHealth: 64,
  turbineStatus: "warning",
  activeAlarmCount: 2,
  evidenceBand: 4,
  consequenceBand: 4,
  matrixRisk: "high",
  riskScore: 16,
  priorityScore: 131.8,
  modelId: "state-matrix-model",
  deploymentId: "state-matrix-deployment",
  featureObservedAt: assessedAt,
  latencyMs: 41,
});

const predictiveMeta = (evaluatedAt: string, count: number, total = count) => ({
  count,
  total,
  filteredTotal: count,
  model: {
    id: "state-matrix-model",
    label: "状态矩阵在线模型",
    mode: "online",
    horizonDays: 30,
    evaluatedAt,
    deterministic: false,
    readOnly: true,
    performsRealInference: true,
    notice: "在线评估结果仅用于测试状态呈现。",
  },
});

const dashboardSnapshot = (snapshotAt: string, empty = false) => ({
  data: {
    snapshot_at: snapshotAt,
    source: "postgresql-timescaledb",
    farm: empty ? null : { id: "WF-STATE-01", name: "状态矩阵风场", capacity_mw: 12 },
    fleet: {
      asset_count: empty ? 0 : 2,
      status_counts: empty ? {} : { running: 1, warning: 1 },
      operating_count: empty ? 0 : 2,
      average_health_score: empty ? null : 82.5,
      current_power_mw: empty ? 0 : 8.4,
      energy_24h_gwh: empty ? null : 0.188,
      energy_coverage_percent: empty ? 0 : 100,
      average_availability_percent: empty ? null : 98.2,
      telemetry_asset_count: empty ? 0 : 2,
      latest_telemetry_at: empty ? null : snapshotAt,
      open_alarm_count: empty ? 0 : 1,
      high_priority_alarm_count: empty ? 0 : 1,
      active_mission_count: empty ? 0 : 1,
    },
    power_trend: empty ? [] : [{ timestamp: snapshotAt, power_mw: 8.4, asset_count: 2 }],
    alarms: empty
      ? []
      : [
          {
            id: "ALARM-STATE-001",
            turbine_id: "WT-901",
            code: "BRG-VIB",
            title: "状态矩阵主轴承告警",
            severity: "major",
            status: "active",
            triggered_at: snapshotAt,
          },
        ],
    missions: empty
      ? []
      : [
          {
            id: "MISSION-STATE-001",
            turbine_id: "WT-901",
            title: "状态矩阵 Mission",
            status: "investigating",
            revision: 4,
            updated_at: snapshotAt,
          },
        ],
    agents: {
      active_definition_count: empty ? 0 : 2,
      execution_count_24h: empty ? 0 : 4,
      succeeded_24h: empty ? 0 : 3,
      failed_24h: empty ? 0 : 1,
    },
    activity: empty
      ? []
      : [
          {
            sequence: 91,
            event_type: "mission.updated",
            aggregate_type: "mission",
            aggregate_id: "MISSION-STATE-001",
            occurred_at: snapshotAt,
            summary: "状态矩阵事件",
          },
        ],
  },
});

const dashboardPartialSnapshot = (snapshotAt: string) => {
  const snapshot = dashboardSnapshot(snapshotAt);
  return {
    data: {
      ...snapshot.data,
      fleet: {
        ...snapshot.data.fleet,
        energy_24h_gwh: null,
        average_availability_percent: null,
      },
    },
  };
};

type PageCase = {
  readonly name: string;
  readonly path: string;
  readonly route: RegExp;
  readonly target: string;
  readonly dataText: string;
  readonly emptyText: string;
  readonly contentSelector: string;
  readonly freshBody: (now: string) => unknown;
  readonly staleBody: (now: string) => unknown;
  readonly emptyBody: (now: string) => unknown;
};

const pageCases: readonly PageCase[] = [
  {
    name: "dashboard",
    path: "/",
    route: /\/api\/backend\/dashboard$/,
    target: "运营指挥数据",
    dataText: "状态矩阵风场",
    emptyText: "当前范围内没有运营数据",
    contentSelector: ".metrics-grid",
    freshBody: (now) => dashboardSnapshot(now),
    staleBody: (now) => dashboardSnapshot(now),
    emptyBody: (now) => dashboardSnapshot(now, true),
  },
  {
    name: "missions",
    path: "/missions",
    route: /\/api\/missions$/,
    target: "Mission 台账",
    dataText: "状态矩阵 Mission",
    emptyText: "当前范围内没有 Mission",
    contentSelector: ".mission-summary",
    freshBody: (now) => ({ data: [mission(now)] }),
    staleBody: (now) => ({ data: [mission(now)] }),
    emptyBody: () => ({ data: [] }),
  },
  {
    name: "decisions",
    path: "/decisions",
    route: /\/api\/decisions$/,
    target: "决策台账",
    dataText: "状态矩阵决策事件",
    emptyText: "当前没有待处理决策",
    contentSelector: ".decision-layout",
    freshBody: (now) => ({ data: [decision(now)] }),
    staleBody: (now) => ({ data: [decision(now)] }),
    emptyBody: () => ({ data: [] }),
  },
  {
    name: "work-orders",
    path: "/work-orders",
    route: /\/api\/work-orders$/,
    target: "工单台账",
    dataText: "状态矩阵主轴承检查",
    emptyText: "当前范围内确实没有工单；权威台账已成功返回空结果。",
    contentSelector: ".work-order-summary",
    freshBody: (now) => ({ data: [workOrder(now)] }),
    staleBody: (now) => ({ data: [workOrder(now)] }),
    emptyBody: () => ({ data: [] }),
  },
  {
    name: "predictive-maintenance",
    path: "/predictive-maintenance",
    route: /\/api\/predictive-assessments(?:\?.*)?$/,
    target: "在线状态评估",
    dataText: "状态矩阵主轴承振动上升",
    emptyText: "尚无成功的在线状态评估",
    contentSelector: "[aria-label='WT-901 预测摘要']",
    freshBody: (now) => ({ data: [assessment(now)], meta: predictiveMeta(now, 1) }),
    staleBody: (now) => ({ data: [assessment(now)], meta: predictiveMeta(now, 1) }),
    emptyBody: (now) => ({ data: [], meta: predictiveMeta(now, 0) }),
  },
];

test.beforeEach(async ({ request }) => {
  await request.post("/__e2e/reset");
});

for (const pageCase of pageCases) {
  test(`${pageCase.name} distinguishes loading, empty, failures, stale data, and recovery`, async ({
    browser,
  }, testInfo) => {
    test.setTimeout(120_000);
    const freshAt = new Date().toISOString();
    const staleAt = new Date(Date.now() - 5 * 60_000).toISOString();

    {
      const { context, page } = await productionPage(browser);
      await installSharedRoutes(page);
      let releaseRequest!: () => void;
      const requestGate = new Promise<void>((resolve) => {
        releaseRequest = resolve;
      });
      await page.route(pageCase.route, async (route) => {
        await requestGate;
        await fulfillJson(route, pageCase.freshBody(freshAt));
      });
      await page.goto(pageCase.path);
      await expect(page.getByText(`正在加载${pageCase.target}`, { exact: true })).toBeVisible();
      await expect(page.locator(pageCase.contentSelector)).toHaveCount(0);
      await expect(page.locator(".empty-state")).toHaveCount(0);
      releaseRequest();
      await expect(page.getByText(pageCase.dataText, { exact: false }).first()).toBeVisible();
      await expect(page.locator(".system-health")).toHaveAttribute("data-health", "ready");
      await context.close();
    }

    {
      const { context, page } = await productionPage(browser);
      await installSharedRoutes(page);
      await page.route(pageCase.route, (route) => fulfillJson(route, pageCase.emptyBody(freshAt)));
      await page.goto(pageCase.path);
      await expect(page.getByText(pageCase.emptyText, { exact: true }).first()).toBeVisible();
      await expect(page.getByText(`正在加载${pageCase.target}`, { exact: true })).toHaveCount(0);
      await expect(page.locator(".system-health")).toHaveAttribute("data-health", "ready");
      await context.close();
    }

    for (const failure of [
      {
        name: "permission",
        status: 403,
        code: "E2E_FORBIDDEN",
        title: `没有权限读取${pageCase.target}`,
        health: "degraded",
      },
      {
        name: "conflict",
        status: 409,
        code: "E2E_REVISION_CONFLICT",
        title: `${pageCase.target}已发生状态冲突`,
        health: "degraded",
      },
      {
        name: "service",
        status: 500,
        code: "E2E_SERVICE_FAILURE",
        title: `${pageCase.target}当前不可用`,
        health: "offline",
      },
      {
        name: "network",
        status: 0,
        code: "NETWORK_FAILURE",
        title: `${pageCase.target}当前不可用`,
        health: "offline",
      },
    ] as const) {
      const { context, page } = await productionPage(browser);
      await installSharedRoutes(page);
      await page.route(pageCase.route, (route) => {
        if (failure.status === 0) return route.abort("internetdisconnected");
        return fulfillJson(
          route,
          { error: { code: failure.code, message: `forced ${failure.name} failure` } },
          failure.status,
          `correlation-${pageCase.name}-${failure.name}`,
        );
      });
      await page.goto(pageCase.path);
      await expect(page.getByText(failure.title, { exact: true }).first()).toBeVisible();
      await expect(page.getByText(failure.code, { exact: false }).first()).toBeVisible();
      await expect(page.getByText("本次会话尚无成功响应", { exact: false }).first()).toBeVisible();
      await expect(page.getByText("关联 ID：", { exact: false }).first()).toBeVisible();
      if (failure.status > 0) {
        await expect(
          page.getByText(`correlation-${pageCase.name}-${failure.name}`, { exact: false }).first(),
        ).toBeVisible();
      }
      await expect(page.locator(pageCase.contentSelector)).toHaveCount(0);
      await expect(page.getByText(pageCase.emptyText, { exact: true })).toHaveCount(0);
      await expect(page.locator(".system-health")).toHaveAttribute("data-health", failure.health);
      await context.close();
    }

    {
      const { context, page } = await productionPage(browser);
      await installSharedRoutes(page);
      let callCount = 0;
      let releaseFailedRefresh!: () => void;
      const failedRefreshGate = new Promise<void>((resolve) => {
        releaseFailedRefresh = resolve;
      });
      await page.route(pageCase.route, async (route) => {
        callCount += 1;
        if (callCount === 1) {
          await fulfillJson(route, pageCase.staleBody(staleAt));
          return;
        }
        if (callCount === 2) {
          await failedRefreshGate;
          await fulfillJson(
            route,
            { error: { code: "E2E_REFRESH_FAILED", message: "forced refresh failure" } },
            500,
            `correlation-${pageCase.name}-refresh`,
          );
          return;
        }
        await fulfillJson(route, pageCase.freshBody(new Date().toISOString()));
      });
      await page.goto(pageCase.path);
      const notice = page.locator(".query-state").filter({
        hasText: `${pageCase.target}不是最新状态`,
      });
      await expect(notice).toBeVisible();
      await expect(page.getByText(pageCase.dataText, { exact: false }).first()).toBeVisible();
      await expect(page.locator(".system-health")).toHaveAttribute("data-health", "stale");

      await notice.getByRole("button", { name: "重试" }).click();
      await expect(page.getByText(`正在刷新${pageCase.target}`, { exact: true })).toBeVisible();
      await expect(page.getByText(pageCase.dataText, { exact: false }).first()).toBeVisible();
      releaseFailedRefresh();
      await expect(page.getByText("E2E_REFRESH_FAILED", { exact: false }).first()).toBeVisible();
      await expect(page.getByText(pageCase.dataText, { exact: false }).first()).toBeVisible();
      await page.screenshot({
        path: testInfo.outputPath(`${pageCase.name}-stale-refresh.png`),
        fullPage: true,
        animations: "disabled",
      });

      await page.locator(".query-state").getByRole("button", { name: "重试" }).click();
      await expect(page.locator(".query-state")).toHaveCount(0);
      await expect(page.locator(".system-health")).toHaveAttribute("data-health", "ready");
      await expect(page.getByText(pageCase.dataText, { exact: false }).first()).toBeVisible();
      await context.close();
    }
  });
}

test("dashboard names partial modules, preserves healthy modules, and recovers in place", async ({
  browser,
}, testInfo) => {
  const { context, page } = await productionPage(browser);
  await installSharedRoutes(page);
  let callCount = 0;
  await page.route(/\/api\/backend\/dashboard$/, (route) => {
    callCount += 1;
    return fulfillJson(
      route,
      callCount === 1
        ? dashboardPartialSnapshot(new Date().toISOString())
        : dashboardSnapshot(new Date().toISOString()),
    );
  });

  await page.goto("/");
  const partial = page.locator(".query-state--partial");
  await expect(partial.getByText("运营快照部分数据不可用", { exact: true })).toBeVisible();
  await expect(partial).toContainText("可利用率遥测");
  await expect(partial).toContainText("AVAILABILITY_UNAVAILABLE");
  await expect(partial).toContainText("24 小时电量");
  await expect(partial).toContainText("ENERGY_WINDOW_INCOMPLETE");
  await expect(page.getByText("状态矩阵风场", { exact: false }).first()).toBeVisible();
  const healthyPowerMetric = page.locator(".metric-card").filter({ hasText: "当前功率" });
  await expect(healthyPowerMetric).toContainText("8.4");
  await expect(page.locator(".system-health")).toHaveAttribute("data-health", "degraded");
  await page.screenshot({
    path: testInfo.outputPath("dashboard-partial-failure.png"),
    fullPage: true,
    animations: "disabled",
  });

  await partial.getByRole("button", { name: "重试失败模块" }).click();
  await expect(partial).toHaveCount(0);
  await expect(page.locator(".system-health")).toHaveAttribute("data-health", "ready");
  await expect(healthyPowerMetric).toContainText("8.4");
  await context.close();
});

test("mission, work-order, and predictive filters distinguish filtered-empty and clear it", async ({
  browser,
}) => {
  const now = new Date().toISOString();

  {
    const { context, page } = await productionPage(browser);
    await installSharedRoutes(page);
    await page.route(/\/api\/missions$/, (route) => fulfillJson(route, { data: [mission(now)] }));
    await page.goto("/missions");
    await page.getByRole("textbox", { name: "搜索 Mission" }).fill("NO-SUCH-MISSION");
    await expect(page.getByText("筛选结果为空", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "清除筛选" }).click();
    await expect(page.getByText("状态矩阵 Mission", { exact: true }).first()).toBeVisible();
    await context.close();
  }

  {
    const { context, page } = await productionPage(browser);
    await installSharedRoutes(page);
    await page.route(/\/api\/work-orders$/, (route) =>
      fulfillJson(route, { data: [workOrder(now)] }),
    );
    await page.goto("/work-orders");
    await page.getByRole("searchbox", { name: "搜索表格" }).fill("NO-SUCH-WORK-ORDER");
    await expect(
      page.getByText("筛选结果为空；请调整条件或使用“清除筛选”。", { exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "清除表格搜索" }).click();
    await expect(page.getByText("状态矩阵主轴承检查", { exact: true }).first()).toBeVisible();
    await context.close();
  }

  {
    const { context, page } = await productionPage(browser);
    await installSharedRoutes(page);
    await page.route(/\/api\/predictive-assessments(?:\?.*)?$/, (route) => {
      const filtered = new URL(route.request().url()).searchParams.get("risk") === "low";
      return fulfillJson(
        route,
        filtered
          ? { data: [], meta: predictiveMeta(now, 0, 1) }
          : { data: [assessment(now)], meta: predictiveMeta(now, 1) },
      );
    });
    await page.goto("/predictive-maintenance");
    await page.getByRole("combobox", { name: "筛选风险" }).selectOption("low");
    await expect(page.getByText("筛选结果为空", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "清除筛选" }).click();
    await expect(page.getByText("状态矩阵主轴承振动上升", { exact: false }).first()).toBeVisible();
    await context.close();
  }
});

test("predictive command exposes long-running and result-unknown recovery with one idempotency key", async ({
  browser,
}, testInfo) => {
  const { context, page } = await productionPage(browser);
  await installSharedRoutes(page);
  const now = new Date().toISOString();
  await page.route(/\/api\/predictive-assessments(?:\?.*)?$/, (route) =>
    fulfillJson(route, { data: [assessment(now)], meta: predictiveMeta(now, 1) }),
  );

  let mode: "running" | "unknown" | "reconcile" = "running";
  let releaseRunning!: () => void;
  const runningGate = new Promise<void>((resolve) => {
    releaseRunning = resolve;
  });
  const observedKeys: string[] = [];
  await page.route("**/api/backend/predictive-assessments/run", async (route) => {
    observedKeys.push(route.request().headers()["idempotency-key"] ?? "");
    if (mode === "running") {
      await runningGate;
      await fulfillJson(route, { count: 1, failed: 0, predictions: [{ status: "completed" }] });
      return;
    }
    if (mode === "unknown") {
      await route.abort("internetdisconnected");
      return;
    }
    await fulfillJson(route, { count: 1, failed: 0, predictions: [{ status: "completed" }] });
  });

  await page.goto("/predictive-maintenance");
  const runButton = page.getByRole("button", { name: "运行在线评估" });
  await runButton.click();
  await expect(page.getByText("在线评估正在运行", { exact: true })).toBeVisible();
  await expect(page.getByText("不提供独立心跳或取消能力", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "评估中…" })).toBeDisabled();
  releaseRunning();
  await expect(page.getByText("在线评估已完成", { exact: true })).toBeVisible();

  mode = "unknown";
  await page.getByRole("button", { name: "运行在线评估" }).click();
  const unknownNotice = page.locator(".query-state--operation");
  await expect(unknownNotice.getByText("在线评估结果尚未确认", { exact: true })).toBeVisible();
  await expect(unknownNotice).toContainText("COMMAND_RESULT_UNKNOWN");
  await expect(unknownNotice).toContainText("不要创建新命令");
  expect(observedKeys.at(-2)).toBe(observedKeys.at(-1));
  const reconciliationKey = observedKeys.at(-1);
  expect(reconciliationKey).toMatch(/^predictive-assessment-run-/);
  await page.screenshot({
    path: testInfo.outputPath("predictive-result-unknown.png"),
    fullPage: true,
    animations: "disabled",
  });

  mode = "reconcile";
  await page.getByRole("button", { name: "使用同一键核验" }).click();
  await expect(page.getByText("在线评估已完成", { exact: true })).toBeVisible();
  expect(observedKeys.at(-1)).toBe(reconciliationKey);
  await expect(page.locator(".access-recovery-banner")).toHaveCount(0);
  await context.close();
});
