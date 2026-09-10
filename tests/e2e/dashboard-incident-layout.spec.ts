import {
  expect,
  test,
  type Browser,
  type BrowserContext,
  type Page,
  type Route,
} from "@playwright/test";

const baseURL = "http://127.0.0.1:4179";

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    headers: { "x-correlation-id": "dashboard-layout-e2e" },
    body: JSON.stringify(body),
  });
}

async function demoPage(browser: Browser, width: number, height: number) {
  const context = await browser.newContext({
    baseURL,
    viewport: { width, height },
    extraHTTPHeaders: { "x-e2e-runtime": "demo" },
  });
  return { context, page: await context.newPage() };
}

function productionSnapshot(snapshotAt: string, alarms: "none" | "single" | "multiple") {
  const alarmRows =
    alarms === "none"
      ? []
      : [
          {
            id: "ALARM-P1-001",
            turbine_id: "WT-901",
            code: "BRG-VIB",
            title: "主轴承振动异常",
            severity: "critical",
            status: "active",
            triggered_at: new Date(Date.parse(snapshotAt) - 48 * 60_000).toISOString(),
          },
          {
            id: "ALARM-P2-002",
            turbine_id: "WT-902",
            code: "OIL-TEMP",
            title: "齿轮箱油温偏高",
            severity: "major",
            status: "active",
            triggered_at: new Date(Date.parse(snapshotAt) - 35 * 60_000).toISOString(),
          },
          {
            id: "ALARM-P2-003",
            turbine_id: "WT-903",
            code: "YAW-ERR",
            title: "偏航误差持续超限",
            severity: "major",
            status: "acknowledged",
            triggered_at: new Date(Date.parse(snapshotAt) - 22 * 60_000).toISOString(),
          },
        ].slice(0, alarms === "single" ? 1 : undefined);
  return {
    data: {
      snapshot_at: snapshotAt,
      source: "postgresql-timescaledb",
      farm: { id: "WF-PROD-01", name: "生产验收风场", capacity_mw: 24 },
      fleet: {
        asset_count: 4,
        status_counts: { running: 3, warning: 1 },
        operating_count: 4,
        average_health_score: 87.5,
        current_power_mw: 18.4,
        energy_24h_gwh: 0.411,
        energy_coverage_percent: 100,
        average_availability_percent: 97.8,
        telemetry_asset_count: 4,
        latest_telemetry_at: snapshotAt,
        open_alarm_count: alarmRows.length,
        high_priority_alarm_count: alarmRows.length,
        active_mission_count: alarms === "none" ? 0 : 1,
      },
      power_trend: Array.from({ length: 12 }, (_, index) => ({
        timestamp: new Date(Date.parse(snapshotAt) - (11 - index) * 15 * 60_000).toISOString(),
        power_mw: 15 + index * 0.3,
        asset_count: 4,
      })),
      alarms: alarmRows,
      missions:
        alarms === "none"
          ? []
          : [
              {
                id: "MISSION-PROD-001",
                turbine_id: "WT-901",
                title: "主轴承诊断 Mission",
                status: "investigating",
                revision: 3,
                updated_at: snapshotAt,
              },
            ],
      agents: {
        active_definition_count: 3,
        execution_count_24h: 8,
        succeeded_24h: 7,
        failed_24h: 1,
      },
      activity: [
        {
          sequence: 101,
          event_type: "mission.updated",
          aggregate_type: "mission",
          aggregate_id: "MISSION-PROD-001",
          occurred_at: snapshotAt,
          summary: "已收集公开诊断证据",
        },
      ],
    },
  };
}

async function productionPage(
  browser: Browser,
  alarms: "none" | "single" | "multiple",
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({
    baseURL,
    viewport: { width: 1440, height: 900 },
    extraHTTPHeaders: {
      "oai-authenticated-user-id": "user-manager",
      "oai-authenticated-user-email": "user-manager@example.com",
    },
  });
  const page = await context.newPage();
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
  await page.route("**/api/backend/dashboard", (route) =>
    fulfillJson(route, productionSnapshot(new Date().toISOString(), alarms)),
  );
  await page.route("**/api/alarms", (route) => fulfillJson(route, { data: [] }));
  return { context, page };
}

async function metricRows(page: Page): Promise<number[]> {
  const boxes = await page
    .locator(".metrics-grid > *")
    .evaluateAll((nodes) => nodes.map((node) => Math.round(node.getBoundingClientRect().top)));
  return [...new Set(boxes)];
}

test("dashboard keeps incident, six KPI, trend, and priority queue in the desktop decision view", async ({
  browser,
}, testInfo) => {
  const { context, page } = await demoPage(browser, 1440, 900);
  await page.goto("/");

  await expect(page.locator(".command-strip")).toBeVisible();
  await expect(page.locator(".metrics-grid > *")).toHaveCount(6);
  expect(await metricRows(page)).toHaveLength(1);
  const power = await page.locator(".panel--power").boundingBox();
  const priority = await page.locator(".panel--priority").boundingBox();
  expect(power).not.toBeNull();
  expect(priority).not.toBeNull();
  expect(Math.abs(power!.y - priority!.y)).toBeLessThan(2);
  expect(power!.width / priority!.width).toBeGreaterThan(1.3);
  expect(power!.width / priority!.width).toBeLessThan(1.5);
  expect((await page.getByText("优先处置队列").boundingBox())!.y).toBeLessThan(900);
  expect((await page.getByText("全场有功功率").boundingBox())!.y).toBeLessThan(900);
  await expect(page.locator(".dashboard-lower-grid > .panel")).toHaveCount(3);

  await page.screenshot({
    path: testInfo.outputPath("dashboard-demo-1440x900.png"),
    fullPage: true,
  });
  const missionLink = page.getByRole("link", { name: "进入 Mission" }).first();
  await missionLink.focus();
  await expect(missionLink).toBeFocused();
  await expect(missionLink).toHaveAttribute("href", /\/missions\//);
  const keyboardActivation = page.evaluate(
    () =>
      new Promise<boolean>((resolve) => {
        document.querySelector(".incident-link")?.addEventListener(
          "click",
          (event) => {
            event.preventDefault();
            resolve(event instanceof MouseEvent && event.detail === 0);
          },
          { once: true },
        );
      }),
  );
  await page.keyboard.press("Enter");
  await expect(keyboardActivation).resolves.toBe(true);
  await context.close();
});

test("dashboard uses a complete 3 by 2 KPI grid at 1280", async ({ browser }, testInfo) => {
  const { context, page } = await demoPage(browser, 1280, 800);
  await page.goto("/");
  await expect(page.locator(".metrics-grid > *")).toHaveCount(6);
  const rows = await metricRows(page);
  expect(rows).toHaveLength(2);
  const counts = await page.locator(".metrics-grid > *").evaluateAll((nodes) => {
    const grouped = new Map<number, number>();
    for (const node of nodes) {
      const top = Math.round(node.getBoundingClientRect().top);
      grouped.set(top, (grouped.get(top) ?? 0) + 1);
    }
    return [...grouped.values()];
  });
  expect(counts).toEqual([3, 3]);
  await page.screenshot({
    path: testInfo.outputPath("dashboard-demo-1280x800.png"),
    fullPage: true,
  });
  await context.close();
});

test("production uses the same incident-first structure for stable, single, and multi-event states", async ({
  browser,
}, testInfo) => {
  const multiple = await productionPage(browser, "multiple");
  await multiple.page.goto("/");
  await expect(multiple.page.getByText("最高优先级 · 需要处置")).toBeVisible();
  await expect(multiple.page.getByRole("link", { name: "进入 Mission" })).toHaveAttribute(
    "href",
    "/missions/MISSION-PROD-001",
  );
  await expect(multiple.page.locator(".metrics-grid > *")).toHaveCount(6);
  await expect(multiple.page.locator(".panel--priority .alarm-row")).toHaveCount(3);
  await multiple.page.screenshot({
    path: testInfo.outputPath("dashboard-production-multiple-1440x900.png"),
    fullPage: true,
  });
  await multiple.context.close();

  const single = await productionPage(browser, "single");
  await single.page.goto("/");
  await expect(single.page.getByText("最高优先级 · 需要处置")).toBeVisible();
  await expect(single.page.locator(".panel--priority .alarm-row")).toHaveCount(1);
  await expect(single.page.getByRole("link", { name: "进入 Mission" })).toHaveAttribute(
    "href",
    "/missions/MISSION-PROD-001",
  );
  await single.page.screenshot({
    path: testInfo.outputPath("dashboard-production-single-1440x900.png"),
    fullPage: true,
  });
  await single.context.close();

  const stable = await productionPage(browser, "none");
  await stable.page.goto("/");
  await expect(stable.page.getByText("当前没有需要立即处置的事件")).toBeVisible();
  await expect(stable.page.getByRole("link", { name: "查看全部告警" })).toHaveAttribute(
    "href",
    "/alarms",
  );
  await expect(stable.page.getByText(/权威快照未返回高优先级告警/)).toBeVisible();
  await stable.page.screenshot({
    path: testInfo.outputPath("dashboard-production-stable-1440x900.png"),
    fullPage: true,
  });
  await stable.context.close();
});
