import { expect, test } from "@playwright/test";

if (process.env.WINDOPS_BUSINESS_E2E !== "1" || process.env.WINDOPS_E2E_REAL_BACKEND !== "1") {
  throw new Error("Use the isolated business E2E runner; fixture success is not accepted here");
}
const identity = (subject: string) => ({
  "oai-authenticated-user-id": subject,
  "oai-authenticated-user-email": `${subject}@example.com`,
});
const manager = identity("business-manager");
const approver = identity("business-approver");
const field = identity("business-field");
const restricted = identity("business-restricted");
const ingestUrl = `${process.env.WINDOPS_E2E_BACKEND_ORIGIN}/api/v1/scada/ingest`;
const ingestHeaders = { Authorization: `Bearer ${process.env.WINDOPS_BUSINESS_E2E_INGEST_KEY}` };

test("real asynchronous diagnosis, browser approval and MinIO evidence close one governed workflow", async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(240_000);
  const observed = new Date(Date.now() - 180_000).toISOString();
  const normal = {
    source_id: "business-e2e",
    samples: [
      {
        source_event_id: "E2E-NORMAL-VIB",
        turbine_id: "WT-023",
        observed_at: observed,
        variable: "main_bearing_vibration_rms",
        value: 3,
        unit: "mm/s",
        quality: "good",
        attributes: { baseline: 3, anomaly_score: 0.08 },
      },
      {
        source_event_id: "E2E-NORMAL-TEMP",
        turbine_id: "WT-023",
        observed_at: observed,
        variable: "main_bearing_temperature",
        value: 67.1,
        unit: "degC",
        quality: "good",
      },
      {
        source_event_id: "E2E-NORMAL-POWER",
        turbine_id: "WT-023",
        observed_at: observed,
        variable: "active_power",
        value: 5.42,
        unit: "MW",
        quality: "good",
      },
    ],
  };
  const normalResponse = await request.post(ingestUrl, {
    headers: ingestHeaders,
    data: normal,
  });
  expect(normalResponse.status()).toBe(202);
  expect((await normalResponse.json()).accepted).toBe(3);
  const anomaly = {
    source_id: "business-e2e",
    samples: [
      {
        source_event_id: "E2E-ANOMALY",
        turbine_id: "WT-023",
        observed_at: new Date(Date.now() - 60_000).toISOString(),
        variable: "main_bearing_vibration_rms",
        value: 4.81,
        unit: "mm/s",
        quality: "good",
        attributes: {
          baseline: 3.79,
          anomaly_score: 0.86,
          temperature_delta_c: 8.4,
          power_fluctuation_pct: 6,
        },
      },
    ],
  };
  const ingest = await request.post(ingestUrl, {
    headers: ingestHeaders,
    data: anomaly,
  });
  expect(ingest.status()).toBe(202);
  const ingested = await ingest.json();
  const missionId = String(ingested.results[0].mission_id);
  const alarmId = String(ingested.results[0].alarm_id);
  expect(missionId).toMatch(/^MISSION-/);
  const duplicateIngest = await request.post(ingestUrl, {
    headers: ingestHeaders,
    data: anomaly,
  });
  expect(duplicateIngest.status()).toBe(202);
  expect((await duplicateIngest.json()).duplicates).toBe(1);
  const missionPath = `/api/backend/missions/${missionId}`;
  await expect
    .poll(
      async () =>
        String((await (await request.get(missionPath, { headers: manager })).json()).status),
      { timeout: 60_000 },
    )
    .toBe("under_review");
  const mission = await (await request.get(missionPath, { headers: manager })).json();
  expect(mission.work_order_id).toBeNull();
  expect(mission.executions).toHaveLength(7);
  const unauthenticated = await request.get(missionPath);
  expect(unauthenticated.status()).toBe(401);
  const hidden = await request.get(missionPath, { headers: restricted });
  expect([403, 404]).toContain(hidden.status());
  expect(await hidden.text()).not.toContain('"turbine_id"');
  const hiddenList = await request.get("/api/backend/missions", { headers: restricted });
  expect(hiddenList.status()).toBe(200);
  expect((await hiddenList.json()).missions).toHaveLength(0);
  const approvalPayload = {
    action: "approve",
    expected_revision: mission.revision,
    selected_alternative_id: mission.decision.recommended_alternative_id,
    reason: "E2E engineering review",
  };
  const forbidden = await request.post(`${missionPath}/approvals`, {
    headers: { ...field, "Idempotency-Key": "business-forbidden-approval" },
    data: approvalPayload,
  });
  expect(forbidden.status()).toBe(403);
  const wrongScope = await request.post(`${missionPath}/approvals`, {
    headers: { ...restricted, "Idempotency-Key": "business-wrong-scope-approval" },
    data: approvalPayload,
  });
  expect([403, 404]).toContain(wrongScope.status());
  const stale = await request.post(`${missionPath}/approvals`, {
    headers: { ...approver, "Idempotency-Key": "business-stale-approval" },
    data: { ...approvalPayload, expected_revision: mission.revision - 1 },
  });
  expect(stale.status()).toBe(409);

  await page.setExtraHTTPHeaders(approver);
  const detailRoute = `**${missionPath}`;
  await page.route(detailRoute, (route) => route.abort("internetdisconnected"));
  await page.goto(`/missions/${missionId}`);
  await expect(page.getByRole("button", { name: "重试" })).toBeVisible({ timeout: 15_000 });
  await page.unroute(detailRoute);
  await page.getByRole("button", { name: "重试" }).click();
  await expect(page.getByRole("button", { name: "批准推荐方案" })).toBeVisible();
  await page.getByLabel("审批原因").fill("E2E engineering review with actual persisted evidence");
  const approvalResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`${missionPath}/approvals`) && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "批准推荐方案" }).dblclick();
  const approved = await approvalResponse;
  expect(approved.status()).toBe(200);
  const approvalBody = await approved.json();
  const workOrderId = String(approvalBody.work_order_id);
  expect(workOrderId).toMatch(/^WO-/);
  const original = approved.request();
  const replay = await request.post(`${missionPath}/approvals`, {
    headers: { ...approver, "Idempotency-Key": original.headers()["idempotency-key"] },
    data: original.postDataJSON(),
  });
  expect(replay.status()).toBe(200);
  expect(replay.headers()["idempotency-replayed"]).toBe("true");
  expect((await replay.json()).work_order_id).toBe(workOrderId);
  const approvedMission = await (await request.get(missionPath, { headers: manager })).json();
  expect(approvedMission.approvals).toHaveLength(1);
  expect(approvedMission.approvals[0].approver).toBe("business-approver");

  const workOrderPath = `/api/backend/work-orders/${workOrderId}`;
  const workOrder = await (await request.get(workOrderPath, { headers: field })).json();
  expect(workOrder.tasks).toHaveLength(5);
  await page.setExtraHTTPHeaders(field);
  await page.goto(`/work-orders?workOrder=${encodeURIComponent(workOrderId)}`);
  const measurements: Record<string, string | number>[] = [
    { lubrication_condition: "acceptable", water_content_ppm: 120 },
    { vibration_rms_mm_s: 3.8, bpfo_band_energy_pct: 4.2 },
    { bearing_temperature_c: 68.4 },
    { defect_severity: "minor", spall_area_mm2: 1.2 },
    { photo_count: 5, main_bearing_health_score: 78, turbine_health_score: 82 },
  ];
  let lastRequest: { url: string; body: unknown; key: string } | undefined;
  for (let index = 0; index < 5; index++) {
    const form = page.locator(".field-evidence-form");
    await expect(form).toBeVisible();
    const task = workOrder.tasks[index];
    for (const [name, value] of Object.entries(measurements[index])) {
      const property = task.measurement_schema.properties[name];
      const control = form.getByLabel(String(property.title ?? name), { exact: false });
      if (Array.isArray(property.enum)) await control.selectOption(String(value));
      else await control.fill(String(value));
    }
    await form
      .getByLabel("现场结论", { exact: false })
      .fill(`Actual uploaded synthetic field evidence for task ${index + 1}`);
    await form.locator('input[type="file"]').setInputFiles({
      name: `evidence-${index}.json`,
      mimeType: "application/json",
      buffer: Buffer.from(
        JSON.stringify({
          fixture: "business-e2e",
          task: index + 1,
          measurement: measurements[index],
        }),
      ),
    });
    const completionResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/tasks/${task.task_id}/complete`) &&
        response.request().method() === "POST",
    );
    await form.getByRole("button", { name: "上传证据并完成任务" }).click();
    const completed = await completionResponse;
    expect(completed.status()).toBe(200);
    const result = await completed.json();
    expect(result.workflow_finalized).toBe(index === 4);
    lastRequest = {
      url: `${workOrderPath}/tasks/${task.task_id}/complete`,
      body: completed.request().postDataJSON(),
      key: completed.request().headers()["idempotency-key"],
    };
    if (index < 4) await expect(form).toContainText(`${index + 2}.`);
  }
  await expect(page.getByText("证据已验证 · 工单已闭环")).toBeVisible();
  expect(lastRequest).toBeDefined();
  const completionReplay = await request.post(lastRequest!.url, {
    headers: { ...field, "Idempotency-Key": lastRequest!.key },
    data: lastRequest!.body,
  });
  expect(completionReplay.status()).toBe(200);
  expect(completionReplay.headers()["idempotency-replayed"]).toBe("true");
  const finalOrder = await (await request.get(workOrderPath, { headers: manager })).json();
  const finalMission = await (await request.get(missionPath, { headers: manager })).json();
  const finalAlarm = await (
    await request.get(`/api/backend/alarms/${alarmId}`, { headers: manager })
  ).json();
  const health = await (
    await request.get("/api/backend/turbines/WT-023/health", { headers: manager })
  ).json();
  const cases = await (
    await request.get(`/api/backend/knowledge/cases?mission_id=${missionId}`, { headers: manager })
  ).json();
  expect(finalOrder.status).toBe("completed");
  expect(finalOrder.tasks.every((task: { status: string }) => task.status === "completed")).toBe(
    true,
  );
  expect(finalMission.status).toBe("completed");
  expect(finalAlarm.status).toBe("resolved");
  expect(health.health_score).toBe(82);
  expect(cases.count).toBe(1);
  await testInfo.attach("persisted-closure", {
    contentType: "application/json",
    body: JSON.stringify({
      missionId,
      workOrderId,
      alarmId,
      approvalCount: finalMission.approvals.length,
      completedTasks: finalOrder.tasks.length,
      healthScore: health.health_score,
      knowledgeCases: cases.count,
    }),
  });
});
