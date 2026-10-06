import { expect, test, type Page } from "@playwright/test";
import { createHash } from "node:crypto";

// Explicit synthetic UI/transport fixtures. They verify actual built UI commands,
// not numerical qualification, object-store verification, or field acceptance.
const asset = "UI-TOWER-1";
const component = "11111111-1111-4111-8111-111111111111";
const tendon = "22222222-2222-4222-8222-222222222222";
const sensor = "33333333-3333-4333-8333-333333333333";
const waveSensor = "88888888-8888-4888-8888-888888888888";
const record = "44444444-4444-4444-8444-444444444444";
const run = "55555555-5555-4555-8555-555555555555";
const secondComponent = "66666666-6666-4666-8666-666666666666";
const training = Array.from(
  { length: 30 },
  (_, index) => `77777777-7777-4777-8777-${String(index + 1).padStart(12, "0")}`,
);
const empty = { items: [], next_cursor: null };

async function baseRoutes(page: Page) {
  await page.route("**/api/backend/turbines?*", (route) =>
    route.fulfill({
      json: {
        turbines: [{ turbine_id: asset, model: "Synthetic browser tower" }],
        next_cursor: null,
      },
    }),
  );
  await page.route(`**/api/backend/turbines/${asset}/tower-components?*`, (route) =>
    route.fulfill({
      json: {
        components: {
          items: [{ id: component, code: "C01", name: "Synthetic joint", revision: "r1" }],
          next_cursor: null,
        },
        tendons: {
          items: [{ id: tendon, component_id: component, code: "T01", revision: "r1" }],
          next_cursor: null,
        },
        sensors: {
          items: [
            {
              id: sensor,
              component_id: component,
              tendon_id: tendon,
              code: "F01",
              revision: "r1",
              quantity: "force",
              calibration_version: "synthetic-cal1",
              calibration_valid_until: "2027-01-01T00:00:00Z",
            },
          ],
          next_cursor: null,
        },
      },
    }),
  );
  await page.route("**/api/backend/turbines/*/structural-health?*", (route) =>
    route.fulfill({
      json: {
        assessment_status: "no_data",
        baseline_status: "unavailable",
        baseline: null,
        analyses: empty,
        prestress: empty,
      },
    }),
  );
  await page.route("**/api/backend/missions?*", (route) =>
    route.fulfill({ json: { missions: [], next_cursor: null } }),
  );
}

test.beforeEach(async ({ context, page }) => {
  await context.setExtraHTTPHeaders({
    "oai-authenticated-user-id": "user-manager",
    "oai-authenticated-user-email": "manager@example.com",
    "x-e2e-runtime": "production",
  });
  await baseRoutes(page);
});

async function openAsset(page: Page) {
  await page.goto("/structural");
  await page.getByLabel("选择授权机组").selectOption(asset);
  await expect(page.getByLabel("采集操作")).toBeVisible();
}

test("versioned component, tendon and calibration commands use actual scoped inputs", async ({
  page,
}) => {
  const calls: { path: string; body: unknown; key: string | undefined }[] = [];
  let releaseComponent!: () => void;
  const componentGate = new Promise<void>((resolve) => {
    releaseComponent = resolve;
  });
  for (const path of ["tower-components", "tendon-assemblies", "sensor-channels"]) {
    await page.route(`**/api/backend/${path}`, async (route) => {
      calls.push({
        path,
        body: route.request().postDataJSON(),
        key: route.request().headers()["idempotency-key"],
      });
      if (path === "tower-components") await componentGate;
      await route.fulfill({
        status: 201,
        json: {
          id:
            path === "tower-components"
              ? secondComponent
              : path === "tendon-assemblies"
                ? tendon
                : sensor,
        },
      });
    });
  }
  await openAsset(page);
  await page.getByLabel("采集操作").selectOption("component");
  const componentForm = page.getByRole("region", { name: "构件建档", exact: true });
  await componentForm.getByLabel("构件编码").fill("C02");
  await componentForm.getByLabel("构件版本").fill("r2");
  await componentForm.getByLabel("构件名称").fill("Synthetic anchor");
  await componentForm.getByLabel("构件类型").selectOption("anchor");
  await componentForm.getByLabel("设计资料引用").fill("synthetic-design/r2");
  await componentForm.getByLabel("父构件（可选）").selectOption(component);
  await componentForm.getByLabel("几何参数 JSON（键名注明单位，可选）").fill('{"height_m":1.25}');
  await componentForm.getByRole("button", { name: "保存构件版本" }).click();
  await expect(page.getByLabel("选择授权机组")).toBeDisabled();
  await expect(page.getByLabel("采集操作")).toBeDisabled();
  await expect(componentForm.getByLabel("构件版本")).toBeDisabled();
  expect(calls).toHaveLength(1);
  releaseComponent();
  await expect(componentForm.getByRole("status")).toContainText(secondComponent);
  await page.getByLabel("采集操作").selectOption("tendon");
  const tendonForm = page.getByRole("region", { name: "索束建档", exact: true });
  await tendonForm.getByLabel("索束编码").fill("T02");
  await tendonForm.getByLabel("索束版本").fill("r2");
  await tendonForm.getByLabel("所属构件").selectOption(component);
  await tendonForm.getByLabel("有效长度 (m，可选)").fill("12.5");
  await tendonForm
    .getByLabel("边界条件 JSON（文字引用，可选）")
    .fill('{"anchor":"synthetic-anchorage/r2"}');
  await tendonForm.getByRole("button", { name: "保存索束版本" }).click();
  await expect(tendonForm.getByRole("status")).toContainText(tendon);
  await page.getByLabel("采集操作").selectOption("sensor");
  const sensorForm = page.getByRole("region", { name: "测点建档", exact: true });
  await sensorForm.getByLabel("测点编码").fill("F02");
  await sensorForm.getByLabel("测点版本").fill("r2");
  await sensorForm.getByLabel("所属构件").selectOption(component);
  await sensorForm.getByLabel("测量类型").selectOption("force");
  await sensorForm.getByLabel("所属索束（索力必填）").selectOption(tendon);
  await sensorForm.getByLabel("测量单位").selectOption("N");
  await sensorForm.getByLabel("测量方向").selectOption("axial");
  await sensorForm.getByLabel("量程下限").fill("0");
  await sensorForm.getByLabel("量程上限").fill("250000");
  await sensorForm.getByLabel("校准版本").fill("synthetic-cal2");
  await sensorForm.getByLabel("校准时间（含时区）").fill("2026-10-01T08:00:00.123456+08:00");
  await sensorForm.getByLabel("校准有效至（含时区）").fill("2027-01-01T08:00:00+08:00");
  await sensorForm.getByLabel("校准资料引用").fill("synthetic-calibration/r2");
  await sensorForm.getByLabel("同步时钟来源").fill("synthetic-PTP");
  await sensorForm.getByRole("button", { name: "保存测点版本" }).click();
  await expect(sensorForm.getByRole("status")).toContainText(sensor);
  expect(calls.map((call) => call.body)).toEqual([
    {
      turbine_id: asset,
      code: "C02",
      revision: "r2",
      name: "Synthetic anchor",
      component_type: "anchor",
      design_reference: "synthetic-design/r2",
      parent_id: component,
      geometry: { height_m: 1.25 },
    },
    {
      turbine_id: asset,
      code: "T02",
      revision: "r2",
      component_id: component,
      effective_length_m: 12.5,
      boundary: { anchor: "synthetic-anchorage/r2" },
    },
    {
      turbine_id: asset,
      code: "F02",
      revision: "r2",
      component_id: component,
      tendon_id: tendon,
      quantity: "force",
      unit: "N",
      direction: "axial",
      range_min: 0,
      range_max: 250000,
      calibration_version: "synthetic-cal2",
      calibration_at: "2026-10-01T08:00:00.123456+08:00",
      calibration_valid_until: "2027-01-01T08:00:00+08:00",
      calibration_reference: "synthetic-calibration/r2",
      synchronization_source: "synthetic-PTP",
    },
  ]);
  expect(new Set(calls.map((call) => call.key)).size).toBe(3);
  expect(calls.every((call) => call.key?.startsWith("structural-"))).toBe(true);
});

test("original waveform and force bytes register without invented environment and analysis polls failures", async ({
  page,
}) => {
  const wave = {
    schema_version: "openvigil.waveform.v1",
    turbine_id: asset,
    started_at: "2026-10-05T08:00:00.123456+08:00",
    sample_rate_hz: 16,
    channels: [
      {
        channel_id: waveSensor,
        unit: "m/s2",
        offset_seconds: 0,
        samples: Array.from({ length: 2048 }, (_, i) => Math.sin(i / 8)),
      },
    ],
  };
  const force = {
    schema_version: "openvigil.direct-force.v1",
    tendon_id: tendon,
    sensor_id: sensor,
    observed_at: "2026-10-05T08:10:00.123456+08:00",
    value: 110000,
    unit: "N",
    calibration_version: "synthetic-cal1",
    uncertainty_kn: 0.25,
  };
  const waveBytes = Buffer.from(JSON.stringify(wave));
  const forceBytes = Buffer.from(JSON.stringify(force));
  const presigns: unknown[] = [];
  const registrations: unknown[] = [];
  const uploads: Buffer[] = [];
  let registered = false;
  let status = "pending";
  let analysisCalls = 0;
  await page.route("**/api/backend/structural-records/uploads/presign", (route) => {
    const body = route.request().postDataJSON();
    presigns.push(body);
    const uri = `minio://synthetic-ui/${body.file_name}`;
    return route.fulfill({
      json: {
        artifact_uri: uri,
        upload_url: `https://upload.example.test/${body.file_name}`,
        required_headers: { "content-type": "application/json" },
        expires_at: "2099-01-01T00:00:00Z",
      },
    });
  });
  await page.route("https://upload.example.test/*", (route) => {
    if (route.request().method() === "OPTIONS")
      return route.fulfill({
        status: 204,
        headers: {
          "access-control-allow-origin": "*",
          "access-control-allow-methods": "PUT",
          "access-control-allow-headers": "content-type",
        },
      });
    uploads.push(route.request().postDataBuffer()!);
    expect(route.request().headers().authorization).toBeUndefined();
    return route.fulfill({ status: 200, headers: { "access-control-allow-origin": "*" } });
  });
  await page.route("**/api/backend/structural-records", (route) => {
    registrations.push(route.request().postDataJSON());
    registered = true;
    return route.fulfill({ status: 201, json: { id: record } });
  });
  await page.route("**/api/backend/prestress-observations", (route) => {
    registrations.push(route.request().postDataJSON());
    return route.fulfill({ status: 201, json: { id: tendon, value_kn: 110 } });
  });
  await page.route("**/api/backend/structural-records?*", (route) =>
    route.fulfill({
      json: {
        items: registered
          ? [{ id: record, started_at: wave.started_at, source_kind: "synthetic_test" }]
          : [],
        next_cursor: null,
      },
    }),
  );
  await page.route("**/api/backend/structural-analyses", (route) => {
    analysisCalls++;
    expect(route.request().postDataJSON()).toEqual({
      record_id: record,
      method: "pyoma2_fdd_v1",
      config: { nperseg: 1024, min_frequency_hz: 0.05, max_frequency_hz: 3, max_modes: 4 },
    });
    return route.fulfill({ status: 202, json: { id: run, status: "pending" } });
  });
  await page.route(`**/api/backend/structural-analyses/${run}`, (route) =>
    route.fulfill({
      json: {
        id: run,
        status,
        attempts: status === "pending" ? 0 : 1,
        error_code: status === "failed" ? "SYNTHETIC_QUALITY_REJECTED" : null,
        result:
          status === "failed"
            ? {
                quality: { usable: false, missing_fraction: 0.2 },
                warnings: ["Synthetic missing channel samples"],
              }
            : null,
        modal_observations: [],
      },
    }),
  );
  await openAsset(page);
  await page.getByLabel("采集操作").selectOption("record");
  const form = page.getByRole("region", { name: "原始结构资料登记" });
  await form.getByLabel("原始结构 JSON 文件").setInputFiles({
    name: "wrong.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify({ ...wave, turbine_id: "OTHER-ASSET" })),
  });
  await expect(form.getByRole("alert")).toBeVisible();
  await expect(form.getByRole("button", { name: "上传并登记原始资料" })).toBeDisabled();
  expect(presigns).toHaveLength(0);
  await form
    .getByLabel("原始结构 JSON 文件")
    .setInputFiles({ name: "wave.json", mimeType: "application/json", buffer: waveBytes });
  await expect(
    form.getByText(`${wave.started_at} → 2026-10-05T00:02:08.123456Z（结束时刻不包含）`),
  ).toBeVisible();
  await form.getByLabel("资料来源分类").selectOption("synthetic_test");
  await form.getByLabel("采集资料引用").fill("Synthetic acquisition UI fixture");
  await form.getByLabel("采集工况").selectOption("stopped");
  await form.getByLabel("温度 (°C，可选)").fill("0");
  await form.getByRole("button", { name: "上传并登记原始资料" }).click();
  await expect(form.getByRole("status")).toContainText(record);
  await expect(form.getByLabel("原始结构 JSON 文件")).toHaveValue("");
  await form
    .getByLabel("原始结构 JSON 文件")
    .setInputFiles({ name: "force.json", mimeType: "application/json", buffer: forceBytes });
  await expect(form.getByText(`110000 N · ${force.observed_at}`)).toBeVisible();
  await expect(form.getByLabel("采集工况")).toHaveCount(0);
  await form.getByRole("button", { name: "上传并登记原始资料" }).click();
  await expect(form.getByRole("status")).toContainText(tendon);
  const waveSha = createHash("sha256").update(waveBytes).digest("hex");
  const forceSha = createHash("sha256").update(forceBytes).digest("hex");
  expect(presigns).toEqual([
    { turbine_id: asset, file_name: "wave.json", artifact_sha256: waveSha },
    { turbine_id: asset, file_name: "force.json", artifact_sha256: forceSha },
  ]);
  expect(uploads).toEqual([waveBytes, forceBytes]);
  expect(registrations).toEqual([
    {
      turbine_id: asset,
      channel_ids: [waveSensor],
      started_at: wave.started_at,
      ended_at: "2026-10-05T00:02:08.123456Z",
      sample_rate_hz: 16,
      sample_count: 2048,
      source_kind: "synthetic_test",
      source_reference: "Synthetic acquisition UI fixture",
      environment: { operating_state: "stopped", temperature_c: 0 },
      artifact_uri: "minio://synthetic-ui/wave.json",
      artifact_sha256: waveSha,
    },
    {
      turbine_id: asset,
      tendon_id: tendon,
      sensor_id: sensor,
      source_kind: "synthetic_test",
      artifact_uri: "minio://synthetic-ui/force.json",
      artifact_sha256: forceSha,
    },
  ]);
  await page.getByLabel("采集操作").selectOption("analysis");
  const analysis = page.getByRole("region", { name: "结构分析提交" });
  await expect(analysis.getByLabel("已登记波形记录")).toHaveValue(record);
  await analysis.getByRole("button", { name: "提交后台分析" }).click();
  await expect(analysis.getByLabel("实际分析结果")).toContainText(`排队中 · ${run}`);
  status = "running";
  await analysis.getByRole("button", { name: "刷新计算状态" }).click();
  await expect(analysis.getByLabel("实际分析结果")).toContainText(`计算中 · ${run}`);
  status = "failed";
  await analysis.getByRole("button", { name: "刷新计算状态" }).click();
  await expect(analysis.getByLabel("实际分析结果")).toContainText("SYNTHETIC_QUALITY_REJECTED");
  await expect(analysis.getByLabel("实际分析结果")).toContainText("usable: false");
  await expect(analysis.getByLabel("实际分析结果")).toContainText(
    "Synthetic missing channel samples",
  );
  expect(analysisCalls).toBe(1);
});

test("baseline requires 30 distinct references and responsibility and replays an unknown publication", async ({
  page,
}) => {
  let calls = 0;
  const keys: (string | undefined)[] = [];
  let firstBody: unknown;
  await page.route("**/api/backend/health-baselines", async (route) => {
    calls++;
    keys.push(route.request().headers()["idempotency-key"]);
    const body = route.request().postDataJSON();
    if (!firstBody) firstBody = body;
    expect(body).toEqual(firstBody);
    if (calls <= 2) {
      await route.abort("failed");
      return;
    }
    await route.fulfill({
      status: 201,
      json: {
        id: "UI-BASELINE-1",
        model: {
          validation: {
            split: "chronological_holdout_20_percent",
            training_count: 24,
            validation_count: 6,
            rmse_hz: 0.001,
          },
          qualification: "requires_field_validation",
        },
      },
    });
  });
  await openAsset(page);
  await page.getByLabel("采集操作").selectOption("baseline");
  const form = page.getByRole("region", { name: "健康基线发布", exact: true });
  await form.getByLabel("基线所属构件").selectOption(component);
  await form.getByLabel("基线编码").fill("BASE-UI");
  await form.getByLabel("基线版本").fill("r1");
  await form.getByLabel("健康确认资料引用").fill("Synthetic healthy window confirmation");
  await form.getByLabel("基线有效至（含时区）").fill("2027-01-01T08:00:00+08:00");
  await form.getByLabel("健康训练模态 ID（每行一个）").fill(training.slice(0, 29).join("\n"));
  await form.getByLabel("参考模态观测").selectOption(training[0]);
  await form.getByLabel("温度", { exact: true }).check();
  await expect(form.getByRole("button", { name: "发布健康基线版本" })).toBeDisabled();
  await form.getByLabel("我确认这些窗口来自资料所指的健康期间，并承担本次基线发布责任。").check();
  await form.getByRole("button", { name: "发布健康基线版本" }).click();
  await expect(form.getByRole("alert")).toBeVisible();
  expect(calls).toBe(0);
  await form
    .getByLabel("健康训练模态 ID（每行一个）")
    .fill([...training.slice(0, 29), training[0]].join("\n"));
  await form.getByLabel("参考模态观测").selectOption(training[0]);
  await form.getByRole("button", { name: "发布健康基线版本" }).click();
  await expect(form.getByRole("alert")).toContainText("重复");
  expect(calls).toBe(0);
  await form.getByLabel("健康训练模态 ID（每行一个）").fill(training.join("\n"));
  await form.getByLabel("参考模态观测").selectOption(training[0]);
  await form.getByRole("button", { name: "发布健康基线版本" }).click();
  await expect(form.getByText("发布结果待核验，使用原训练引用和版本重试。")).toBeVisible();
  await expect(form.getByLabel("基线版本")).toBeDisabled();
  await expect(page.getByLabel("选择授权机组")).toBeDisabled();
  await expect(page.getByLabel("采集操作")).toBeDisabled();
  await form.getByRole("button", { name: "核验原基线发布" }).click();
  await expect(form.getByText("实际发布版本 UI-BASELINE-1")).toBeVisible();
  await expect(form.getByText(/training_count: 24；validation_count: 6/)).toBeVisible();
  await expect(form.getByRole("button", { name: "发布健康基线版本" })).toBeDisabled();
  expect(calls).toBe(3);
  expect(new Set(keys).size).toBe(1);
  expect(firstBody).toEqual({
    turbine_id: asset,
    component_id: component,
    code: "BASE-UI",
    revision: "r1",
    confirmation_reference: "Synthetic healthy window confirmation",
    reference_modal_id: training[0],
    training_modal_ids: training,
    features: ["temperature_c"],
    valid_until: "2027-01-01T08:00:00+08:00",
    minimum_mac: 0.9,
    maximum_relative_frequency_shift: 0.2,
    screening_sigma: 3,
  });
});

test("independent cursor navigation keeps loaded choices and clears them on asset switch", async ({
  page,
}) => {
  const urls: URL[] = [];
  await page.route(`**/api/backend/turbines/${asset}/tower-components?*`, (route) => {
    const url = new URL(route.request().url());
    urls.push(url);
    const second = Boolean(url.searchParams.get("component_cursor"));
    return route.fulfill({
      json: {
        components: {
          items: [
            {
              id: second ? secondComponent : component,
              code: second ? "C02" : "C01",
              name: "Synthetic paged component",
              revision: "r1",
            },
          ],
          next_cursor: second ? null : "component+page/2=",
        },
        tendons: {
          items: [{ id: tendon, component_id: component, code: "T01", revision: "r1" }],
          next_cursor: "tendon+page/2=",
        },
        sensors: { items: [], next_cursor: "sensor+page/2=" },
      },
    });
  });
  await page.route("**/api/backend/turbines?*", (route) =>
    route.fulfill({
      json: {
        turbines: [
          { turbine_id: asset, model: "Synthetic tower" },
          { turbine_id: "UI-TOWER-2", model: "Synthetic second tower" },
        ],
        next_cursor: null,
      },
    }),
  );
  await page.route("**/api/backend/turbines/UI-TOWER-2/tower-components?*", (route) =>
    route.fulfill({ json: { components: empty, tendons: empty, sensors: empty } }),
  );
  await openAsset(page);
  await page.getByLabel("采集操作").selectOption("tendon");
  const form = page.getByRole("region", { name: "索束建档", exact: true });
  await form.getByLabel("索束编码").fill("Synthetic unsaved draft");
  await form.getByLabel("所属构件").selectOption(component);
  await page.getByRole("button", { name: "构件下页", exact: true }).click();
  await expect(page.getByRole("button", { name: "构件上页", exact: true })).toBeEnabled();
  await expect(form.getByLabel("所属构件").locator("option")).toHaveCount(3);
  await expect(form.getByLabel("所属构件")).toHaveValue(component);
  await expect(form.getByLabel("索束编码")).toHaveValue("Synthetic unsaved draft");
  await page.getByRole("button", { name: "索束下页", exact: true }).click();
  await expect.poll(() => urls.at(-1)?.searchParams.get("tendon_cursor")).toBe("tendon+page/2=");
  expect(urls.at(-1)?.searchParams.get("component_cursor")).toBe("component+page/2=");
  expect(urls.at(-1)?.searchParams.get("sensor_cursor")).toBe("");
  await page.getByRole("button", { name: "构件上页", exact: true }).click();
  await expect.poll(() => urls.at(-1)?.searchParams.get("component_cursor")).toBe("");
  expect(urls.at(-1)?.searchParams.get("tendon_cursor")).toBe("tendon+page/2=");
  await page.getByRole("button", { name: "索束首页", exact: true }).click();
  await expect(page.getByRole("button", { name: "索束上页", exact: true })).toBeDisabled();
  await page.getByLabel("选择授权机组").selectOption("UI-TOWER-2");
  await page.getByLabel("采集操作").selectOption("tendon");
  await expect(
    page
      .getByRole("region", { name: "索束建档", exact: true })
      .getByLabel("所属构件")
      .locator("option"),
  ).toHaveCount(1);
  await expect(
    page.getByRole("region", { name: "索束建档", exact: true }).getByLabel("索束编码"),
  ).toHaveValue("");
});

test("asset, observation and Mission cursors retain original selected identities", async ({
  page,
}) => {
  await page.route("**/api/backend/turbines?*", (route) => {
    const next = Boolean(new URL(route.request().url()).searchParams.get("cursor"));
    return route.fulfill({
      json: {
        turbines: [{ turbine_id: next ? "UI-TOWER-2" : asset, model: "Synthetic paged asset" }],
        next_cursor: next ? null : "asset+page/2=",
      },
    });
  });
  await page.route(`**/api/backend/turbines/${asset}/structural-health?*`, (route) => {
    const next = Boolean(new URL(route.request().url()).searchParams.get("prestress_cursor"));
    return route.fulfill({
      json: {
        assessment_status: "requires_engineering_review",
        baseline_status: "unavailable",
        baseline: null,
        analyses: empty,
        prestress: {
          items: [
            {
              id: next ? record : sensor,
              tendon_id: tendon,
              sensor_id: sensor,
              value_kn: next ? 109 : 110,
              observed_at: "2026-10-05T00:00:00Z",
              source_kind: "synthetic_test",
            },
          ],
          next_cursor: next ? null : "force+page/2=",
        },
      },
    });
  });
  await page.route("**/api/backend/missions?*", (route) => {
    const next = Boolean(new URL(route.request().url()).searchParams.get("cursor"));
    return route.fulfill({
      json: {
        missions: [
          {
            mission_id: next ? "M-SYNTHETIC-SECOND" : "M-SYNTHETIC-FIRST",
            title: next ? "Synthetic second review" : "Synthetic first review",
            work_order_id: null,
            analysis_profile: { component: "hybrid_tower_structure" },
          },
        ],
        next_cursor: next ? null : "mission+page/2=",
      },
    });
  });
  await page.route("**/api/backend/structural-missions/M-SYNTHETIC-FIRST", (route) =>
    route.fulfill({
      json: {
        mission_id: "M-SYNTHETIC-FIRST",
        revision: 1,
        claim_id: null,
        scenario: "prestress_retest",
        status: "under_review",
        missing_evidence: [],
        comparison: {},
        evidence_cards: [],
      },
    }),
  );
  await openAsset(page);
  await page.getByLabel("构件", { exact: true }).selectOption(component);
  await page.getByLabel("复核场景").selectOption("prestress_retest");
  await page.getByLabel("直接索力观测").selectOption(sensor);
  await page.getByLabel("选择实际任务").selectOption("M-SYNTHETIC-FIRST");
  await page.getByRole("button", { name: "机组下页", exact: true }).click();
  await expect(page.getByLabel("选择授权机组").locator("option")).toHaveCount(3);
  await expect(page.getByLabel("选择授权机组")).toHaveValue(asset);
  await page.getByRole("button", { name: "索力下页", exact: true }).click();
  await expect(page.getByLabel("直接索力观测").locator("option")).toHaveCount(3);
  await expect(page.getByLabel("直接索力观测")).toHaveValue(sensor);
  await page.getByRole("button", { name: "任务下页", exact: true }).click();
  await expect(page.getByLabel("选择实际任务").locator("option")).toHaveCount(3);
  await expect(page.getByLabel("选择实际任务")).toHaveValue("M-SYNTHETIC-FIRST");
  for (const label of ["机组", "索力", "任务"]) {
    await page.getByRole("button", { name: `${label}上页`, exact: true }).click();
    await expect(page.getByRole("button", { name: `${label}上页`, exact: true })).toBeDisabled();
  }
  await expect(page.getByLabel("选择实际任务")).toHaveValue("M-SYNTHETIC-FIRST");
  await expect(page.getByLabel("直接索力观测")).toHaveValue(sensor);
  const missionForm = page.getByRole("button", { name: "提交结构复核" }).locator("..");
  const [formWidth, fieldWidth] = await Promise.all([
    missionForm.evaluate((element) => element.getBoundingClientRect().width),
    page
      .getByLabel("构件", { exact: true })
      .evaluate((element) => element.getBoundingClientRect().width),
  ]);
  expect(fieldWidth).toBeGreaterThan(formWidth * 0.4);
  expect(fieldWidth).toBeLessThan(formWidth * 0.6);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: ".artifacts/hybrid-tower-20261005/structural-acquisition-desktop.png",
    fullPage: true,
  });
});

test("field role sees raw acquisition while configuration and baseline require their owners", async ({
  page,
  context,
}) => {
  await context.setExtraHTTPHeaders({
    "oai-authenticated-user-id": "user-field",
    "oai-authenticated-user-email": "field@example.com",
    "x-e2e-runtime": "production",
  });
  await openAsset(page);
  const select = page.getByLabel("采集操作");
  await expect(select.locator('option[value="record"]')).toHaveJSProperty("disabled", false);
  for (const value of ["component", "tendon", "sensor", "analysis", "baseline"]) {
    await expect(select.locator(`option[value="${value}"]`)).toHaveJSProperty("disabled", true);
  }
  await select.selectOption("record");
  await expect(page.getByRole("region", { name: "原始结构资料登记" })).toBeVisible();
  await expect(page.getByRole("button", { name: "提交结构复核" })).toBeDisabled();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true);
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
    path: ".artifacts/hybrid-tower-20261005/structural-acquisition-mobile.png",
    fullPage: true,
  });
});
