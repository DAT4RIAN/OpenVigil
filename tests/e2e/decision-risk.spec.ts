import { expect, test } from "@playwright/test";

test("unknown deterioration risk stays distinct from zero on desktop and mobile", async ({
  page,
}, testInfo) => {
  await page.setExtraHTTPHeaders({
    "oai-authenticated-user-id": "user-approver",
    "oai-authenticated-user-email": "user-approver@example.com",
  });
  const now = new Date().toISOString();
  const alternative = {
    id: "ALT-UNKNOWN",
    label: "方案 A",
    title: "受控检查",
    description: "明确合成的界面测试方案",
    safetyRisk: "high",
    deteriorationRiskPercent: null as number | null,
    estimatedCostCny: 15000,
    estimatedDowntimeHours: 10,
    estimatedEnergyLossMWh: 8,
    weatherWindowId: null,
    requiredResources: [],
    recommended: true,
    rationale: "概率证据不足。",
  };
  const decision = {
    id: "DEC-UNKNOWN",
    missionId: "MISSION-E2E-001",
    missionRevision: 1,
    turbineId: "WT-E2E-01",
    incident: "未知风险显示验证",
    diagnosis: "明确合成的界面测试诊断",
    confidencePercent: 86,
    status: "under-review",
    risk: "high",
    evidenceIds: [],
    alternatives: [alternative],
    recommendedAlternativeId: alternative.id,
    recommendedAction: alternative.title,
    weatherWindowId: null,
    requiredResources: [],
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
  };
  await page.route("**/api/decisions", (route) => route.fulfill({ json: { data: [decision] } }));
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/decisions");
    const card = page.locator(".alternative-card");
    await expect(card.getByText("未评估", { exact: true })).toBeVisible();
    await expect(card).not.toContainText("0%");
    await expect(page.locator(".selected-plan-facts")).toContainText("未评估");
    await expect(page.locator(".decision-factor-grid")).toContainText("所选方案恶化概率：未评估");
    await expect(page.locator("main").first()).not.toContainText(/null%|undefined%/);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(
      true,
    );
    await card.screenshot({ path: testInfo.outputPath(`unknown-risk-${width}.png`) });
  }
  alternative.deteriorationRiskPercent = 0;
  await page.reload();
  await expect(page.locator(".alternative-card").getByText("0%", { exact: true })).toBeVisible();
  await expect(page.locator(".alternative-card")).not.toContainText("未评估");
  expect(errors).toEqual([]);
});
