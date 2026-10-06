import { expect, test } from "@playwright/test";
import { createHash } from "node:crypto";

// Browser interaction contract fixtures. Real database locks and source verification
// are covered separately; this suite does not establish field or MinIO acceptance.
const componentId = "11111111-1111-4111-8111-111111111111";
const sourceId = "22222222-2222-4222-8222-222222222222";
const card = {
  evidence_id: `prestress:${sourceId}`,
  reference: { kind: "prestress", source_id: sourceId, relation: "supports" },
  turbine_id: "UI-TOWER-1",
  component_id: componentId,
  time_window: { started_at: "2026-10-05T00:00:00Z", ended_at: "2026-10-05T00:00:00Z" },
  source: { sha256: "a".repeat(64), artifact_uri: "minio://synthetic-ui/force.json" },
  method: { method: "direct_force", calibration_version: "synthetic-cal1" },
  measurements: [{ name: "direct_force", value: 110, unit: "kN" }],
  quality: { usable: true },
  uncertainty: { force_kn: 0.25 },
  applicability: { source_kind: "synthetic_test" },
  valid_until: "2027-01-01T00:00:00Z",
  source_fingerprint: "b".repeat(64),
};
const context = {
  mission_id: "M-SYNTHETIC-UI",
  revision: 3,
  claim_id: "33333333-3333-4333-8333-333333333333",
  scenario: "prestress_retest",
  status: "executing",
  missing_evidence: [],
  comparison: { value_kn: 110, damage_probability: null, status: "requires_review" },
  evidence_cards: [card],
};

test.beforeEach(async ({ context, page }) => {
  await context.setExtraHTTPHeaders({
    "oai-authenticated-user-id": "user-manager",
    "oai-authenticated-user-email": "manager@example.com",
    "x-e2e-runtime": "production",
  });
  await page.route("**/api/backend/turbines?*", (route) =>
    route.fulfill({
      json: {
        turbines: [{ turbine_id: "UI-TOWER-1", model: "Synthetic browser tower" }],
        next_cursor: null,
      },
    }),
  );
  await page.route("**/api/backend/turbines/UI-TOWER-1/tower-components?*", (route) =>
    route.fulfill({
      json: {
        components: {
          items: [{ id: componentId, code: "C01", name: "Synthetic joint", revision: "r1" }],
          next_cursor: null,
        },
        tendons: { items: [], next_cursor: null },
        sensors: { items: [], next_cursor: null },
      },
    }),
  );
  await page.route("**/api/backend/turbines/UI-TOWER-1/structural-health?*", (route) =>
    route.fulfill({
      json: {
        assessment_status: "requires_engineering_review",
        baseline_status: "unavailable",
        baseline: null,
        analyses: { items: [], next_cursor: null },
        prestress: {
          items: [
            {
              id: sourceId,
              value_kn: 110,
              tendon_id: componentId,
              sensor_id: componentId,
              observed_at: "2026-10-05T00:00:00Z",
              source_kind: "synthetic_test",
            },
          ],
          next_cursor: null,
        },
      },
    }),
  );
  await page.route("**/api/backend/missions?*", (route) =>
    route.fulfill({
      json: {
        missions: [
          {
            mission_id: "M-SYNTHETIC-UI",
            title: "Synthetic controlled review",
            work_order_id: "WO-SYNTHETIC-UI",
            analysis_profile: { component: "hybrid_tower_structure" },
          },
        ],
        next_cursor: null,
      },
    }),
  );
});

test("structural Mission freezes actual selected source and preserves missing bounds", async ({
  page,
}) => {
  let calls = 0;
  let created = false;
  await page.route("**/api/backend/missions?*", (route) =>
    route.fulfill({
      json: {
        missions: created
          ? [
              {
                mission_id: context.mission_id,
                title: "Synthetic UI retest",
                work_order_id: null,
                analysis_profile: { component: "hybrid_tower_structure" },
              },
            ]
          : [],
        next_cursor: null,
      },
    }),
  );
  await page.route("**/api/backend/structural-missions", async (route) => {
    calls += 1;
    const body = route.request().postDataJSON();
    expect(body).toEqual({
      turbine_id: "UI-TOWER-1",
      component_id: componentId,
      scenario: "prestress_retest",
      source_id: sourceId,
      title: "Synthetic UI retest",
      planning_duration_hours: 1.5,
    });
    expect(route.request().headers()["idempotency-key"]).toMatch(/^structural-/);
    created = true;
    await route.fulfill({ status: 202, json: { ...context, claim_id: null } });
  });
  await page.route("**/api/backend/structural-missions/M-SYNTHETIC-UI", (route) =>
    route.fulfill({ json: { ...context, claim_id: null } }),
  );
  await page.goto("/structural");
  await page.getByLabel("选择授权机组").selectOption("UI-TOWER-1");
  await expect(page.getByText("110 kN · 2026-10-05T00:00:00Z · synthetic_test")).toBeVisible();
  await page.getByLabel("构件", { exact: true }).selectOption(componentId);
  await page.getByLabel("复核场景").selectOption("prestress_retest");
  await page.getByLabel("直接索力观测").selectOption(sourceId);
  await page.getByLabel("任务标题").fill("Synthetic UI retest");
  await page.getByLabel("人工估计复测时长 (小时)").fill("1.5");
  await page.getByRole("button", { name: "提交结构复核" }).click();
  await expect(page.getByText("结构 Mission 已提交，后台将生成待审工程结论。")).toBeVisible();
  expect(calls).toBe(1);
});

test("claim, health review and case publication carry independent revisions", async ({ page }) => {
  let approved = false;
  let completed = false;
  let published = false;
  await page.route("**/api/backend/structural-missions/M-SYNTHETIC-UI", (route) =>
    route.fulfill({
      json: {
        ...context,
        revision: completed ? 4 : 3,
        status: completed ? "completed" : "executing",
      },
    }),
  );
  await page.route(`**/api/backend/engineering-claims/${context.claim_id}`, (route) =>
    route.fulfill({
      json: {
        id: context.claim_id,
        revision: approved ? 2 : 1,
        conclusion: "Synthetic source-grounded retest only",
        effective_status: approved ? "approved" : "pending",
        review_status: approved ? "approved" : "pending",
        created_by: "synthetic-other-author",
        valid_until: "2027-01-01T00:00:00Z",
        missing_evidence: [],
        applicability: {},
        evidence_cards: [card],
        reviews: [],
      },
    }),
  );
  await page.route(
    `**/api/backend/engineering-claims/${context.claim_id}/review`,
    async (route) => {
      expect(route.request().postDataJSON()).toEqual({
        expected_revision: 1,
        action: "approve",
        reason: "Synthetic independent claim review",
      });
      approved = true;
      await route.fulfill({ json: { revision: 2, effective_status: "approved" } });
    },
  );
  await page.route("**/api/backend/structural-work-orders/WO-SYNTHETIC-UI", (route) =>
    route.fulfill({
      json: {
        work_order: {
          id: "WO-SYNTHETIC-UI",
          title: "Synthetic field retest",
          status: completed ? "completed" : "awaiting_health_review",
          mission_id: context.mission_id,
        },
        context,
        tasks: [
          {
            id: sourceId,
            sequence: 1,
            status: "completed",
            title: "Synthetic measured force",
            measurement_schema: {},
          },
        ],
        health_reviews: [],
      },
    }),
  );
  await page.route(
    "**/api/backend/structural-work-orders/WO-SYNTHETIC-UI/health-review",
    async (route) => {
      expect(route.request().postDataJSON()).toEqual({
        expected_mission_revision: 3,
        action: "resolve_review",
        reason: "Synthetic independent health review",
        hypothesis_outcome: "not_supported",
      });
      completed = true;
      await route.fulfill({ json: { mission_revision: 4, work_order_status: "completed" } });
    },
  );
  await page.route("**/api/backend/structural-cases?*", (route) =>
    route.fulfill({
      json: {
        items:
          completed && !published
            ? [
                {
                  case: {
                    id: "CASE-SYNTHETIC-UI",
                    title: "Synthetic pending review case",
                    resolution: {
                      hypothesis_outcome: "not_supported",
                      responsible_reviewer: "synthetic-other-reviewer",
                    },
                  },
                  review: {
                    status: "pending",
                    revision: 1,
                    reviewed_by: null,
                    review_reason: null,
                  },
                },
              ]
            : [],
        next_cursor: null,
      },
    }),
  );
  await page.route("**/api/backend/structural-cases/CASE-SYNTHETIC-UI/review", async (route) => {
    expect(route.request().postDataJSON()).toEqual({
      expected_revision: 1,
      action: "approve",
      reason: "Synthetic independent health review",
    });
    published = true;
    await route.fulfill({ json: { status: "approved", revision: 2 } });
  });
  await page.goto("/structural");
  await page.getByLabel("选择授权机组").selectOption("UI-TOWER-1");
  await page.getByLabel("选择实际任务").selectOption("M-SYNTHETIC-UI");
  await expect(page.getByText("direct_force: 110 kN", { exact: true })).toBeVisible();
  await page.getByLabel("工程审核意见").fill("Synthetic independent claim review");
  await page.getByRole("button", { name: "审核复测建议", exact: true }).click();
  await expect(page.getByText("工程结论审核已保存。")).toBeVisible();
  await page.getByLabel("健康复核意见").fill("Synthetic independent health review");
  await page.getByLabel("异常假设复核结果").selectOption("not_supported");
  await page.getByRole("button", { name: "保存复核并关单" }).click();
  await expect(page.getByText("Synthetic pending review case")).toBeVisible();
  await expect(page.getByText("已完成 · 修订 4", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "审核进入检索" }).click();
  await expect(page.getByText("尚无待审案例。")).toBeVisible();
  expect(approved && completed && published).toBe(true);
  await page.screenshot({
    path: ".artifacts/hybrid-tower-20261005/structural-workflow-ui.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("heading", { name: "混塔结构工作台", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
});

test("structural data errors expose retry and never substitute a synthetic healthy score", async ({
  page,
}) => {
  let fail = true;
  await page.route("**/api/backend/turbines/UI-TOWER-1/structural-health?*", (route) =>
    route.fulfill(
      fail
        ? {
            status: 503,
            json: {
              error: { code: "SYNTHETIC_FAILURE", message: "Synthetic storage unavailable" },
            },
          }
        : {
            json: {
              assessment_status: "no_data",
              baseline_status: "unavailable",
              baseline: null,
              analyses: { items: [], next_cursor: null },
              prestress: { items: [], next_cursor: null },
            },
          },
    ),
  );
  await page.goto("/structural");
  await page.getByLabel("选择授权机组").selectOption("UI-TOWER-1");
  await expect(page.getByText("Synthetic storage unavailable").first()).toBeVisible();
  fail = false;
  await page.getByRole("button", { name: "重试", exact: true }).last().click();
  await expect(page.getByText("尚无模态或直接索力观测。")).toBeVisible();
  await expect(page.getByRole("button", { name: "提交结构复核" })).toBeDisabled();
});

test("follow-up uploads preserve original revision through PUT failure and lost committed response", async ({
  page,
}) => {
  const freshId = "44444444-4444-4444-8444-444444444444";
  const reviewId = "55555555-5555-4555-8555-555555555555";
  const content = Buffer.from(
    '{"source_kind":"synthetic_test","note":"new registered force handoff"}',
  );
  const sha = createHash("sha256").update(content).digest("hex");
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  let uploads = 0;
  let presigns = 0;
  let handoffCalls = 0;
  let published = false;
  const commandKeys: string[] = [];
  const handoff = {
    id: "SYNTHETIC-UI-HANDOFF",
    health_review_id: reviewId,
    modal_id: null,
    prestress_id: freshId,
    artifact_uri: "minio://synthetic-ui/work-orders/WO-SYNTHETIC-UI/tasks/T2/followup.json",
    artifact_sha256: sha,
    measurement: {
      retest_source_id: freshId,
      measurement_reference: "Synthetic new calibrated force",
    },
    verified_by: "synthetic-field-technician",
    verified_at: "2026-10-05T03:05:00Z",
  };
  const orderContext = () => ({ ...context, claim_id: null, revision: handoffCalls ? 5 : 4 });
  await page.route("**/api/backend/structural-missions/M-SYNTHETIC-UI", (route) =>
    route.fulfill({ json: orderContext() }),
  );
  await page.route("**/api/backend/structural-work-orders/WO-SYNTHETIC-UI", (route) =>
    route.fulfill({
      json: {
        work_order: {
          id: "WO-SYNTHETIC-UI",
          mission_id: context.mission_id,
          title: "Synthetic repeated retest",
          status: "awaiting_health_review",
        },
        context: orderContext(),
        tasks: [
          {
            id: "T2",
            sequence: 2,
            title: "Synthetic initial handoff",
            status: "completed",
            measurement_schema: {},
          },
        ],
        health_reviews: [
          {
            id: reviewId,
            action: "requires_followup",
            reason: "Synthetic out-of-bounds result",
            reviewed_by: "synthetic-health-reviewer",
            created_at: "2026-10-05T02:00:00Z",
            assessment: { eligible_to_resolve_review: false },
          },
        ],
        retest_handoffs: published ? [handoff] : [],
      },
    }),
  );
  await page.route("**/api/backend/structural-cases?*", (route) =>
    route.fulfill({ json: { items: [], next_cursor: null } }),
  );
  await page.route("**/api/backend/turbines/UI-TOWER-1/structural-health?*", (route) =>
    route.fulfill({
      json: {
        assessment_status: "requires_engineering_review",
        baseline_status: "unavailable",
        baseline: null,
        analyses: { items: [], next_cursor: null },
        prestress: {
          items: [
            {
              id: sourceId,
              value_kn: 110,
              tendon_id: componentId,
              sensor_id: componentId,
              observed_at: "2026-10-05T00:00:00Z",
              source_kind: "synthetic_test",
            },
            {
              id: freshId,
              value_kn: 125,
              tendon_id: componentId,
              sensor_id: componentId,
              observed_at: "2026-10-05T03:00:00Z",
              source_kind: "synthetic_test",
            },
          ],
          next_cursor: null,
        },
      },
    }),
  );
  await page.route(
    "**/api/backend/structural-work-orders/WO-SYNTHETIC-UI/retests/uploads/presign",
    async (route) => {
      presigns++;
      expect(route.request().postDataJSON()).toEqual({
        file_name: "followup.json",
        content_type: "application/json",
        artifact_sha256: sha,
      });
      await route.fulfill({
        json: {
          artifact_uri: handoff.artifact_uri,
          upload_url: "https://upload.example.test/synthetic-followup",
          required_headers: { "content-type": "application/json" },
          expires_at: "2099-01-01T00:00:00Z",
        },
      });
    },
  );
  await page.route("https://upload.example.test/synthetic-followup", async (route) => {
    if (route.request().method() === "OPTIONS") {
      await route.fulfill({
        status: 204,
        headers: {
          "access-control-allow-origin": "*",
          "access-control-allow-methods": "PUT",
          "access-control-allow-headers": "content-type",
        },
      });
      return;
    }
    uploads++;
    expect(route.request().postDataBuffer()).toEqual(content);
    expect(route.request().headers().authorization).toBeUndefined();
    await route.fulfill({
      status: uploads === 1 ? 503 : 200,
      headers: { "access-control-allow-origin": "*" },
    });
  });
  await page.route(
    "**/api/backend/structural-work-orders/WO-SYNTHETIC-UI/retests",
    async (route) => {
      handoffCalls++;
      expect(route.request().postDataJSON()).toEqual({
        expected_mission_revision: 4,
        result: "Synthetic new force handoff after review",
        measurement: handoff.measurement,
        artifact_uri: handoff.artifact_uri,
        artifact_sha256: sha,
      });
      commandKeys.push(route.request().headers()["idempotency-key"]);
      if (handoffCalls <= 2) {
        await route.abort("failed");
        return;
      }
      published = true;
      await route.fulfill({
        status: 201,
        json: {
          evidence: handoff,
          mission_revision: 5,
          work_order_status: "awaiting_health_review",
        },
      });
    },
  );
  const documentResponse = await page.goto("/structural");
  expect(documentResponse?.headers()["content-security-policy"]).toContain(
    "connect-src 'self' https://upload.example.test;",
  );
  await page.getByLabel("选择授权机组").selectOption("UI-TOWER-1");
  await page.getByLabel("选择实际任务").selectOption("M-SYNTHETIC-UI");
  const form = page.getByRole("region", { name: "追加复测提交" });
  await expect(form).toBeVisible();
  await expect(form.getByLabel("新采集索力观测").locator("option")).toHaveCount(2);
  await form.getByLabel("新采集索力观测").selectOption(freshId);
  await form.getByLabel("追加测量记录引用").fill("Synthetic new calibrated force");
  await form.getByLabel("追加现场结论").fill("Synthetic new force handoff after review");
  await form
    .getByLabel("追加复测证据文件")
    .setInputFiles({ name: "followup.json", mimeType: "application/json", buffer: content });
  await form.getByRole("button", { name: "上传并提交追加复测" }).click();
  await expect(form.getByRole("alert")).toHaveText("对象存储上传失败（HTTP 503）。");
  expect(handoffCalls).toBe(0);
  await form.getByRole("button", { name: "上传并提交追加复测" }).click();
  await expect(
    form.getByText("提交结果待核验。表单保持冻结，重试将使用原测量、修订和幂等键。"),
  ).toBeVisible();
  await expect(form.getByLabel("新采集索力观测")).toBeDisabled();
  await expect(page.getByLabel("选择授权机组")).toBeDisabled();
  await expect(page.getByLabel("选择实际任务")).toBeDisabled();
  await expect(page.getByRole("button", { name: "保存复核并关单" })).toBeDisabled();
  await page.getByRole("button", { name: "刷新复核状态" }).click();
  await expect(form.getByText(`关联复核 ${reviewId} · Mission 修订 5`)).toBeVisible();
  await form.getByRole("button", { name: "核验原复测提交" }).click();
  await expect(
    page
      .getByRole("region", { name: "追加复测历史" })
      .getByText(`观测 ${freshId} · 关联复核 ${reviewId}`),
  ).toBeVisible();
  await expect(form.getByText("追加复测已保存，等待独立健康复核。")).toBeVisible();
  await expect(page.getByLabel("选择授权机组")).toBeEnabled();
  expect(presigns).toBe(1);
  expect(uploads).toBe(2);
  expect(handoffCalls).toBe(3);
  expect(new Set(commandKeys).size).toBe(1);
  expect(errors).toEqual([]);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await expect(page.locator("#openvigil-primary-sidebar")).toHaveAttribute("aria-hidden", "true");
  await expect
    .poll(() =>
      page
        .locator("#openvigil-primary-sidebar")
        .evaluate((element) => element.getBoundingClientRect().right),
    )
    .toBeLessThanOrEqual(0);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: ".artifacts/hybrid-tower-20261005/structural-retest-ui.png",
    fullPage: true,
  });
});
