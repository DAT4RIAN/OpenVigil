import { expect, test } from "@playwright/test";

const planId = `workplan:${"c".repeat(64)}`;
const mission = {
  mission_id: "MISSION-E2E-REVIEWS",
  alarm_id: "ALARM-E2E-REVIEWS",
  turbine_id: "WT-E2E-001",
  title: "Synthetic maintenance review display",
  status: "under_review",
  revision: 3,
  public_state: {
    diagnosis: { conclusion: "Synthetic inspection case" },
    review_target: {
      scope: "maintenance_execution",
      alternative_id: "INSPECT-1",
      execution_plan_id: planId,
    },
    reviews: [
      {
        review_type: "safety",
        reviewer_agent: "Synthetic safety reviewer",
        outcome: "fail",
        public_summary: "Isolation is unavailable for the proposed work.",
        conditions: ["Confirm lockout before inspection"],
        operating_constraints: ["Do not restart before the field assessment"],
      },
    ],
  },
  work_order_id: null,
  evidence: [],
  decision: {
    decision_id: "DECISION-E2E-REVIEWS",
    status: "pending_approval",
    recommendation_reason: "Synthetic local UI fixture",
    recommended_alternative_id: "INSPECT-1",
    selected_alternative_id: null,
    alternatives: [
      {
        alternative_id: "INSPECT-1",
        title: "主轴承受控检查",
        action: "Inspect the main bearing under the controlled procedure",
        execution_plan_id: planId,
      },
    ],
  },
  approvals: [],
  executions: [],
  created_at: "2026-09-27T00:00:00Z",
  updated_at: "2026-09-27T00:00:00Z",
};

test.beforeEach(async ({ page }) => {
  await page.setExtraHTTPHeaders({
    "oai-authenticated-user-id": "user-approver",
    "oai-authenticated-user-email": "user-approver@example.com",
  });
});

test("approval page exposes failed reviews, work prerequisites and operation restrictions", async ({
  page,
}, testInfo) => {
  await page.route("**/api/backend/missions/MISSION-E2E-REVIEWS", (route) =>
    route.fulfill({ json: mission }),
  );
  await page.goto("/missions/MISSION-E2E-REVIEWS");
  await expect(page.getByRole("heading", { name: "维护方案审查" })).toBeVisible();
  const panel = page.getByRole("region", { name: "维护方案审查" });
  await expect(panel.getByText("未通过", { exact: true })).toBeVisible();
  await expect(panel.getByText("Confirm lockout before inspection")).toBeVisible();
  await expect(panel.getByText("Do not restart before the field assessment")).toBeVisible();
  await expect(panel.getByText("主轴承受控检查", { exact: true })).toBeVisible();
  await expect(page.getByText(mission.decision.alternatives[0].action)).toBeVisible();
  await panel.screenshot({ path: testInfo.outputPath("review-desktop.png") });
});

test("legacy review without a target is identified and an unbound proposal cannot be approved", async ({
  page,
}) => {
  const legacy = structuredClone(mission);
  const state = { diagnosis: legacy.public_state.diagnosis, reviews: legacy.public_state.reviews };
  const payload = {
    ...legacy,
    public_state: state,
    decision: {
      ...legacy.decision,
      alternatives: [{ ...legacy.decision.alternatives[0], execution_plan_id: null }],
    },
  };
  await page.route("**/api/backend/missions/MISSION-E2E-REVIEWS", (route) =>
    route.fulfill({ json: payload }),
  );
  await page.goto("/missions/MISSION-E2E-REVIEWS");
  await expect(page.getByText("此审查未注明对象，请结合原始记录复核。")).toBeVisible();
  await page
    .getByRole("textbox", { name: "审批原因", exact: true })
    .fill("Synthetic approval test");
  await expect(page.getByRole("button", { name: "批准推荐方案" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "驳回", exact: true })).toBeEnabled();
});

test("unknown review outcomes remain visible without overflowing a phone viewport", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const payload = structuredClone(mission);
  payload.public_state.reviews[0].outcome = "constructor";
  payload.public_state.reviews[0].review_type = "constructor";
  await page.route("**/api/backend/missions/MISSION-E2E-REVIEWS", (route) =>
    route.fulfill({ json: payload }),
  );
  await page.goto("/missions/MISSION-E2E-REVIEWS");
  const panel = page.getByRole("region", { name: "维护方案审查" });
  await expect(panel.getByText("未知结论", { exact: true })).toBeVisible();
  await expect(panel.getByText("部分审查记录格式不完整，请刷新或检查原始记录。")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await panel.screenshot({ path: testInfo.outputPath("review-mobile.png") });
});

test("failed analysis remains visible and refresh reads status without retrying the model", async ({
  page,
}, testInfo) => {
  const failed = {
    ...mission,
    status: "detected",
    decision: null,
    public_state: {},
    executions: [
      {
        execution_id: "EXECUTION-SYNTHETIC-FAILED",
        node: "reviews",
        agent_role: "review_committee",
        status: "failed",
        latency_ms: 45000,
        provider: "litellm",
        model: "synthetic-model",
        started_at: "2026-09-27T00:00:00Z",
        evaluation_result: { status: "failed", error_code: "provider_timeout" },
      },
    ],
  };
  const methods: string[] = [];
  await page.route("**/api/backend/missions/MISSION-E2E-REVIEWS", (route) => {
    methods.push(route.request().method());
    return route.fulfill({ json: methods.length === 1 ? failed : mission });
  });
  await page.goto("/missions/MISSION-E2E-REVIEWS");
  await expect(page.getByRole("alert").filter({ hasText: "最近一次分析执行失败" })).toBeVisible();
  await expect(page.getByText("模型响应超时。", { exact: true })).toBeVisible();
  await expect(page.getByText("Agent 分析仍在进行，尚无持久化决策。")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "批准推荐方案" })).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("failed-analysis.png"), fullPage: true });
  await page.getByRole("button", { name: "刷新分析状态", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "最近一次分析执行失败" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "批准推荐方案" })).toBeVisible();
  expect(methods).toEqual(["GET", "GET"]);
});
