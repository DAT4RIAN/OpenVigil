import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";

const baseURL = "http://127.0.0.1:4179";

interface E2eState {
  readonly approvalCalls: ReadonlyArray<{
    readonly subject: string;
    readonly body: { readonly action: string };
    readonly idempotencyKey: string;
  }>;
  readonly calls: Record<string, number>;
}

function identityHeaders(subject: string) {
  return {
    "oai-authenticated-user-id": subject,
    "oai-authenticated-user-email": `${subject}@example.com`,
  };
}

async function rolePage(
  browser: Browser,
  subject: string,
  viewport = { width: 1440, height: 900 },
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({
    baseURL,
    viewport,
    extraHTTPHeaders: identityHeaders(subject),
  });
  return { context, page: await context.newPage() };
}

test.beforeEach(async ({ request }) => {
  await request.post("/__e2e/reset");
});

test("production authenticates before business rendering and rejects machine shells", async ({
  request,
}) => {
  const anonymous = await request.get("/missions?status=open", { maxRedirects: 0 });
  expect(anonymous.status()).toBe(302);
  const location = new URL(anonymous.headers().location, baseURL);
  expect(location.pathname).toBe("/signin-with-chatgpt");
  expect(location.searchParams.get("return_to")).toBe("/missions?status=open");
  expect(await anonymous.text()).not.toContain("Mission 中心");

  for (const machine of ["machine-scada", "machine-eam"]) {
    const response = await request.get("/settings", {
      headers: identityHeaders(machine),
      maxRedirects: 0,
    });
    expect(response.status()).toBe(403);
    const html = await response.text();
    expect(html).toContain("当前账号没有 OpenVigil 访问权限");
    expect(html).not.toContain("创建配置修订");
  }

  const demo = await request.get("/", { headers: { "x-e2e-runtime": "demo" } });
  expect(demo.status()).toBe(200);
  expect(await demo.text()).toContain("运营指挥中心");
});

test("field technician gets capability-aware desktop/mobile navigation, refresh, and sign-out", async ({
  browser,
}) => {
  const { context, page } = await rolePage(browser, "user-field");
  await page.goto("/settings");

  await expect(page.locator('[data-authenticated-subject="user-field"]')).toBeVisible();
  await expect(page.getByText("field_technician")).toBeVisible();
  await expect(page.getByText(/创建配置修订需要运维经理和全局平台授权/)).toBeVisible();
  await expect(page.getByRole("button", { name: "创建配置修订" })).toBeDisabled();
  await expect(page.locator('nav a[href="/models"]')).toHaveCount(0);

  await page.reload();
  await expect(page.locator('[data-authenticated-subject="user-field"]')).toBeVisible();
  const storage = await page.evaluate(() => ({
    local: Object.entries(localStorage),
    session: Object.entries(sessionStorage),
  }));
  expect(JSON.stringify(storage)).not.toMatch(/field_technician|platform\.manage|bearer|token/i);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.locator('[data-authenticated-subject="user-field"]')).toBeVisible();
  await page.getByRole("button", { name: "打开导航" }).click();
  await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible();
  await expect(page.locator('nav a[href="/models"]')).toHaveCount(0);
  await page.locator(".sidebar__mobile-close").click();

  const signOut = page.locator('a[title="安全退出 OpenVigil"]');
  await expect(signOut).toHaveAttribute("href", "/signout-with-chatgpt?return_to=%2F");
  await signOut.click();
  await expect(page).toHaveURL(/\/signout-with-chatgpt\?return_to=%2F$/);
  await expect(page.getByRole("heading", { name: "Sites dispatcher sign-out" })).toBeVisible();
  await context.close();
});

test("manager, approver, reviewer, and field technician see only backend-issued mission actions", async ({
  browser,
  request,
}) => {
  const expected = [
    {
      subject: "user-manager",
      visible: ["升级处理"],
      absent: ["批准推荐方案", "驳回", "要求修订"],
      comment: true,
    },
    {
      subject: "user-approver",
      visible: ["批准推荐方案", "驳回"],
      absent: ["升级处理", "要求修订"],
      comment: true,
    },
    {
      subject: "user-reviewer",
      visible: ["要求修订"],
      absent: ["升级处理", "批准推荐方案", "驳回"],
      comment: false,
    },
    {
      subject: "user-field",
      visible: [],
      absent: ["升级处理", "批准推荐方案", "驳回", "要求修订"],
      comment: true,
    },
  ];

  for (const entry of expected) {
    const { context, page } = await rolePage(browser, entry.subject);
    await page.goto(entry.subject === "user-approver" ? "/alarms" : "/missions/MISSION-E2E-001");
    if (entry.subject === "user-approver") {
      const alarmRow = page.locator("tbody tr").filter({ hasText: "E2E bearing alarm" });
      await expect(alarmRow).toBeVisible();
      await alarmRow.focus();
      await page.keyboard.press("Enter");
      const drawer = page.getByRole("dialog", { name: /ALARM-E2E-001 告警详情/ });
      await expect(drawer).toBeVisible();
      await drawer.getByRole("link", { name: /打开完整诊断 Mission/ }).click();
      await expect(page).toHaveURL(/\/missions\/MISSION-E2E-001$/);
    }
    await expect(page.getByRole("heading", { name: "正在读取权威记录" })).toBeVisible();
    await expect(page.getByText("E2E bearing review", { exact: true }).first()).toBeVisible();
    for (const label of entry.visible)
      await expect(page.getByRole("button", { name: label })).toBeVisible();
    for (const label of entry.absent)
      await expect(page.getByRole("button", { name: label })).toHaveCount(0);
    if (entry.comment) await expect(page.getByRole("button", { name: "添加评论" })).toBeEnabled();
    else await expect(page.getByRole("button", { name: "添加评论" })).toBeDisabled();

    if (entry.subject === "user-approver") {
      await page
        .locator('[data-capability="mission.approval"] input')
        .fill("E2E controlled approval");
      await page.getByRole("button", { name: "批准推荐方案" }).dblclick();
      await expect(page.getByRole("status")).toContainText("WO-E2E-001");
    }
    await context.close();
  }

  const state = (await (await request.get("/__e2e/state")).json()) as E2eState;
  expect(state.approvalCalls).toHaveLength(1);
  expect(state.approvalCalls[0].subject).toBe("user-approver");
  expect(state.approvalCalls[0].body.action).toBe("approve");
  expect(state.approvalCalls[0].idempotencyKey).toMatch(/^mission-approve-/);
});

test("decision approval controls fail closed by backend-issued role capability", async ({
  browser,
}) => {
  const now = new Date().toISOString();
  const payload = {
    data: [
      {
        id: "DECISION-ROLE-001",
        missionId: "MISSION-E2E-001",
        missionRevision: 7,
        turbineId: "WT-E2E-01",
        incident: "Role matrix decision",
        diagnosis: "Role capabilities must control each approval action independently.",
        confidencePercent: 86,
        status: "under-review",
        risk: "high",
        evidenceIds: [],
        alternatives: [
          {
            id: "ALT-ROLE-001",
            label: "方案 A",
            title: "受控检查",
            description: "在受控窗口完成检查。",
            safetyRisk: "low",
            deteriorationRiskPercent: 12,
            estimatedCostCny: 68000,
            estimatedDowntimeHours: 4,
            estimatedEnergyLossMWh: 9.2,
            weatherWindowId: null,
            requiredResources: ["海维测试组"],
            recommended: true,
            rationale: "满足安全边界。",
          },
        ],
        recommendedAlternativeId: "ALT-ROLE-001",
        recommendedAction: "受控检查",
        weatherWindowId: null,
        requiredResources: ["海维测试组"],
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
        createdAt: now,
        updatedAt: now,
      },
    ],
  };
  const expectations = [
    { subject: "user-manager", enabled: ["升级处理"] },
    { subject: "user-approver", enabled: ["拒绝", "批准方案"] },
    { subject: "user-reviewer", enabled: ["要求修订"] },
    { subject: "user-field", enabled: [] },
  ] as const;
  const actions = ["拒绝", "要求修订", "升级处理", "批准方案"] as const;

  for (const entry of expectations) {
    const { context, page } = await rolePage(browser, entry.subject);
    await page.route("**/api/decisions", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(payload),
      }),
    );
    await page.goto("/decisions");
    await expect(page.getByText("Role matrix decision", { exact: true }).first()).toBeVisible();
    const reason = page.getByRole("textbox", { name: "审批理由" });
    if (entry.enabled.length > 0) {
      await expect(reason).toBeEnabled();
      await reason.fill("role matrix approval reason");
    } else {
      await expect(reason).toBeDisabled();
    }
    for (const action of actions) {
      const button = page.getByRole("button", { name: action, exact: true });
      await expect(button).toBeVisible();
      if ((entry.enabled as readonly string[]).includes(action)) await expect(button).toBeEnabled();
      else await expect(button).toBeDisabled();
    }
    await context.close();
  }
});

test("401, 403, backend-unready, and browser network failures have distinct recovery UI", async ({
  browser,
  request,
}) => {
  for (const entry of [
    { subject: "user-error-401", kind: "authentication", action: "重新登录" },
    { subject: "user-error-403", kind: "authorization", action: "重试" },
    { subject: "user-error-503", kind: "backend", action: "重试" },
  ]) {
    const { context, page } = await rolePage(browser, entry.subject);
    await page.goto("/settings");
    const banner = page.locator(`.access-recovery-banner[data-access-kind="${entry.kind}"]`);
    await expect(banner).toBeVisible();
    await expect(banner.getByRole("button", { name: entry.action })).toBeVisible();
    if (entry.subject === "user-error-503") {
      await request.post("/__e2e/recover?subject=user-error-503");
      await banner.getByRole("button", { name: "重试" }).click();
      await expect(page.locator('.access-recovery-banner[data-access-kind="backend"]')).toHaveCount(
        0,
      );
      await expect(page.getByRole("button", { name: "创建配置修订" })).toBeVisible();
    }
    await context.close();
  }

  const { context, page } = await rolePage(browser, "user-manager");
  await page.route("**/api/backend/platform/**", (route) => route.abort("internetdisconnected"));
  await page.goto("/settings");
  const networkBanner = page.locator('.access-recovery-banner[data-access-kind="network"]');
  await expect(networkBanner).toBeVisible();
  await expect(networkBanner).toContainText("网络连接失败");
  await context.close();
});

test("production EventSource reconnects with a persisted non-sensitive cursor", async ({
  browser,
  request,
}) => {
  const { context, page } = await rolePage(browser, "user-field");
  await page.goto("/alarms");
  await expect(page.getByRole("heading", { name: /告警中心/ })).toBeVisible();
  await page.getByRole("button", { name: /^严重 0 需立即处理$/ }).click();
  await expect(page.getByText("没有符合当前筛选条件的告警")).toBeVisible();
  await expect
    .poll(async () => {
      const state = (await (await request.get("/__e2e/state")).json()) as E2eState;
      return state.calls["GET /api/v1/events/stream"] ?? 0;
    })
    .toBeGreaterThanOrEqual(2);
  await expect
    .poll(() => page.evaluate(() => sessionStorage.getItem("windops.production-events.alarms.v1")))
    .toBe("42");
  const stored = await page.evaluate(() => JSON.stringify(Object.entries(sessionStorage)));
  expect(stored).not.toMatch(/field_technician|bearer|token|mission\.approve/i);
  await context.close();
});

test("P1 incident remains readable at 320/360/390/430 px with long and 200% text", async ({
  browser,
}) => {
  const { context, page } = await rolePage(browser, "demo-user", { width: 390, height: 900 });
  await page.setExtraHTTPHeaders({ "x-e2e-runtime": "demo" });

  for (const width of [320, 360, 390, 430]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    const incident = page.locator(".command-strip");
    await expect(incident).toBeVisible();
    const title = incident.locator(".incident-title-link");
    const link = incident.locator(".incident-link");

    for (const value of [
      "超长中文主轴承振动异常需要立即开展多专业联合检查与持续跟踪",
      "Extremely long main bearing vibration anomaly requiring coordinated inspection",
      "UNBROKEN_MAIN_BEARING_VIBRATION_ANOMALY_WITHOUT_ANY_BREAK_OPPORTUNITY_2026",
    ]) {
      await title.evaluate((node, text) => {
        node.textContent = text;
        node.style.fontSize = "200%";
      }, value);
      const geometry = await incident.evaluate((node) => {
        const index = node.querySelector(".incident-index")!.getBoundingClientRect();
        const copy = node.querySelector(".incident-copy")!.getBoundingClientRect();
        const signals = node.querySelector(".incident-signals")!.getBoundingClientRect();
        const action = node.querySelector(".incident-link")!.getBoundingClientRect();
        const viewportWidth = document.documentElement.clientWidth;
        return {
          viewportWidth,
          documentWidth: document.documentElement.scrollWidth,
          copyWidth: copy.width,
          separatedFromIndex: copy.left >= index.right - 1,
          signalsBelowCopy: signals.top >= copy.bottom - 1,
          actionBelowCopy: action.top >= copy.bottom - 1,
          actionHeight: action.height,
          overflowing: [...document.querySelectorAll("body *")]
            .filter((element) => element.getBoundingClientRect().right > viewportWidth + 1)
            .slice(0, 8)
            .map((element) => ({
              className: element.className,
              right: Math.round(element.getBoundingClientRect().right),
              text: element.textContent?.trim().slice(0, 80),
            })),
        };
      });
      expect(geometry.overflowing).toEqual([]);
      expect(geometry.documentWidth).toBeLessThanOrEqual(geometry.viewportWidth);
      expect(geometry.copyWidth).toBeGreaterThan(180);
      expect(geometry.separatedFromIndex).toBe(true);
      expect(geometry.signalsBelowCopy).toBe(true);
      expect(geometry.actionBelowCopy).toBe(true);
      expect(geometry.actionHeight).toBeGreaterThanOrEqual(44);
    }

    const actionHref = await link.getAttribute("href");
    expect(actionHref).toMatch(/^\/missions\/MISSION-/);
    await link.focus();
    await expect(link).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(`${baseURL}${actionHref}`);
  }

  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto("/");
  await expect(page.locator(".command-strip")).toHaveScreenshot("dashboard-p1-incident-390.png", {
    animations: "disabled",
    maxDiffPixelRatio: 0.01,
  });
  await context.close();
});
