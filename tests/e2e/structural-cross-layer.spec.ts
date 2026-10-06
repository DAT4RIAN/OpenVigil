import { createHash, randomUUID } from "node:crypto";
import { writeFileSync } from "node:fs";
import { expect, test, type APIRequestContext, type APIResponse } from "@playwright/test";

if (process.env.WINDOPS_E2E_STRUCTURAL !== "1" || process.env.WINDOPS_E2E_REAL_BACKEND !== "1") {
  throw new Error("Run the isolated business E2E runner with --scenario structural");
}
const identity = (subject: string) => ({
  "oai-authenticated-user-id": subject,
  "oai-authenticated-user-email": `${subject}@example.com`,
});
const manager = "business-manager";
const reviewer = "business-reviewer";
const api = "/api/backend/";
const rejectedAuditReads: string[] = [];

async function assertAuditRejection(response: APIResponse) {
  expect(response.status()).toBe(503);
  const body = await response.json();
  expect(Object.keys(body)).toEqual(["error"]);
  expect(body.error.code).toBe("READ_AUDIT_UNAVAILABLE");
  rejectedAuditReads.push(new URL(response.url()).pathname);
}

interface BackendRead {
  id: string;
  status: string;
  revision: number;
  sourceRevision: string;
  modal_observations: { id: string; frequency_hz: number }[];
  algorithm_identity: { adapter_sha256: string };
  public_state: { engineering_claim_id: string };
  passages: { passage_id: string; text: string }[];
  tasks: { id: string }[];
}

async function get(request: APIRequestContext, path: string, subject = manager) {
  const response = await request.get(api + path, { headers: identity(subject) });
  expect(response.status(), await response.text()).toBe(200);
  return response.json() as Promise<BackendRead>;
}

// Validate an audit rejection and retain evidence while waiting for the real
// terminal state within the existing deadline. Every other error fails.
async function pollRead<T>(
  request: APIRequestContext,
  path: string,
  select: (body: BackendRead) => T,
  rejected: T,
): Promise<T> {
  const response = await request.get(api + path, { headers: identity(manager) });
  if (response.status() === 503) {
    await assertAuditRejection(response);
    return rejected;
  }
  expect(response.status(), await response.text()).toBe(200);
  return select((await response.json()) as BackendRead);
}

async function command(
  request: APIRequestContext,
  path: string,
  data: unknown,
  subject = manager,
  status = 201,
  key: string = randomUUID(),
) {
  const response = await request.post(api + path, {
    headers: { ...identity(subject), "Idempotency-Key": key },
    data,
  });
  expect(response.status(), await response.text()).toBe(status);
  return response;
}

async function upload(
  request: APIRequestContext,
  path: string,
  content: Buffer,
  data: Record<string, unknown>,
  subject = manager,
) {
  const sha = createHash("sha256").update(content).digest("hex");
  const response = await command(request, path, { ...data, artifact_sha256: sha }, subject, 200);
  const presigned = await response.json();
  const put = await request.put(presigned.upload_url, {
    data: content,
    headers: presigned.required_headers,
  });
  expect(put.status()).toBe(200);
  return { artifact_uri: presigned.artifact_uri, artifact_sha256: sha };
}

test("real structural queue, browser upload, independent review, closure and Neo4j access", async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(540_000);
  const componentBody = {
    turbine_id: "WT-023",
    code: "SYNTHETIC-E2E-C1",
    name: "软件挑战混塔段",
    component_type: "concrete_segment",
    revision: "r1",
    design_reference: "Synthetic software challenge; no OEM or site qualification",
  };
  const componentKey = randomUUID();
  const component = await (
    await command(request, "tower-components", componentBody, manager, 201, componentKey)
  ).json();
  const replay = await command(
    request,
    "tower-components",
    componentBody,
    manager,
    201,
    componentKey,
  );
  expect(replay.headers()["idempotency-replayed"]).toBe("true");
  expect(await replay.json()).toEqual(component);
  const sensors: { id: string }[] = [];
  for (let index = 0; index < 2; index++) {
    sensors.push(
      await (
        await command(request, "sensor-channels", {
          turbine_id: "WT-023",
          component_id: component.id,
          code: `SYNTHETIC-A${index}`,
          revision: "r1",
          quantity: "acceleration",
          unit: "m/s2",
          direction: "X",
          range_min: -10,
          range_max: 10,
          calibration_version: "synthetic-cal1",
          calibration_at: "2026-01-01T00:00:00Z",
          calibration_valid_until: "2027-01-01T00:00:00Z",
          calibration_reference: "Synthetic fixture only",
          synchronization_source: "synthetic-clock",
        })
      ).json(),
    );
  }
  const started = new Date(Date.now() - 86_400_000);
  const waveform = {
    schema_version: "openvigil.waveform.v1",
    turbine_id: "WT-023",
    started_at: started.toISOString(),
    sample_rate_hz: 16,
    channels: sensors.map((sensor, index) => ({
      channel_id: sensor.id,
      unit: "m/s2",
      offset_seconds: 0,
      samples: Array.from(
        { length: 4096 },
        (_, n) => Math.sin((2 * Math.PI * 0.5 * n) / 16) * (1 + index / 2),
      ),
    })),
  };
  const bytes = Buffer.from(JSON.stringify(waveform));
  await page.setExtraHTTPHeaders(identity(manager));
  await page.goto("/structural");
  await page.getByLabel("选择授权机组").selectOption("WT-023");
  await page.getByLabel("采集操作").selectOption("record");
  const recordForm = page.getByRole("region", { name: "原始结构资料登记" });
  await recordForm.getByLabel("原始结构 JSON 文件").setInputFiles({
    name: "synthetic-wave.json",
    mimeType: "application/json",
    buffer: bytes,
  });
  await recordForm.getByLabel("资料来源分类").selectOption("synthetic_test");
  await recordForm
    .getByLabel("采集资料引用")
    .fill("Synthetic sinusoid; real service software test");
  await recordForm.getByLabel("采集工况").selectOption("stopped");
  await recordForm.getByLabel("转速 (rpm，可选)").fill("0");
  const registered = page.waitForResponse(
    (response) =>
      response.url().endsWith(api + "structural-records") && response.request().method() === "POST",
  );
  const uploaded = page.waitForEvent("requestfinished", {
    predicate: (response) =>
      response.method() === "PUT" &&
      new URL(response.url()).pathname.includes("structural/turbines/WT-023/"),
  });
  await recordForm.getByRole("button", { name: "上传并登记原始资料" }).click();
  const uploadedRequest = await uploaded;
  expect((await uploadedRequest.response())?.status()).toBe(200);
  const recordResponse = await registered;
  expect(recordResponse.status(), await recordResponse.text()).toBe(201);
  const record = await recordResponse.json();
  expect(record.artifact_sha256).toBe(createHash("sha256").update(bytes).digest("hex"));
  await page.getByLabel("采集操作").selectOption("analysis");
  const analysisForm = page.getByRole("region", { name: "结构分析提交" });
  await analysisForm.getByLabel("已登记波形记录").selectOption(record.id);
  const submitted = page.waitForResponse(
    (response) =>
      response.url().endsWith(api + "structural-analyses") &&
      response.request().method() === "POST",
  );
  await analysisForm.getByRole("button", { name: "提交后台分析" }).click();
  const queued = await submitted;
  expect(queued.status()).toBe(202);
  const run = await queued.json();
  expect(run.status).toBe("pending");
  await expect
    .poll(
      async () =>
        pollRead(
          request,
          `structural-analyses/${run.id}`,
          (body) => body.status,
          "audit_unavailable",
        ),
      {
        timeout: 120_000,
      },
    )
    .toBe("succeeded");
  const completed = await get(request, `structural-analyses/${run.id}`);
  expect(completed.modal_observations.length).toBeGreaterThan(0);
  expect(completed.modal_observations[0].frequency_hz).toBeCloseTo(0.5, 6);
  expect(completed.algorithm_identity.adapter_sha256).toMatch(/^[a-f0-9]{64}$/);
  await analysisForm.getByRole("button", { name: "刷新计算状态" }).click();
  await expect(analysisForm.getByLabel("实际分析结果")).toContainText(run.id);
  const restricted = await request.get(api + `structural-analyses/${run.id}`, {
    headers: identity("business-restricted"),
  });
  expect([403, 404]).toContain(restricted.status());
  expect(await restricted.text()).not.toContain(record.id);
  const badWave = {
    ...waveform,
    channels: waveform.channels.map((channel) => ({
      ...channel,
      samples: Array(4096).fill(0),
    })),
  };
  const badArtifact = await upload(
    request,
    "structural-records/uploads/presign",
    Buffer.from(JSON.stringify(badWave)),
    { turbine_id: "WT-023", file_name: "flat.json" },
  );
  const badRecord = await (
    await command(request, "structural-records", {
      turbine_id: "WT-023",
      channel_ids: sensors.map((sensor) => sensor.id),
      started_at: started.toISOString(),
      ended_at: new Date(started.getTime() + 256_000).toISOString(),
      sample_rate_hz: 16,
      sample_count: 4096,
      ...badArtifact,
      source_kind: "synthetic_test",
      source_reference: "Synthetic flat-line rejection challenge",
      environment: { operating_state: "stopped" },
    })
  ).json();
  const badRun = await (
    await command(
      request,
      "structural-analyses",
      {
        record_id: badRecord.id,
        config: {},
      },
      manager,
      202,
    )
  ).json();
  await expect
    .poll(
      async () =>
        pollRead(
          request,
          `structural-analyses/${badRun.id}`,
          (body) => body.status,
          "audit_unavailable",
        ),
      {
        timeout: 120_000,
      },
    )
    .toBe("insufficient_data");
  expect((await get(request, `structural-analyses/${badRun.id}`)).modal_observations).toEqual([]);

  const tendon = await (
    await command(request, "tendon-assemblies", {
      turbine_id: "WT-023",
      component_id: component.id,
      code: "SYNTHETIC-T1",
      revision: "r1",
      boundary: { anchor: "Synthetic calibration fixture" },
    })
  ).json();
  const forceSensor = await (
    await command(request, "sensor-channels", {
      turbine_id: "WT-023",
      component_id: component.id,
      tendon_id: tendon.id,
      code: "SYNTHETIC-F1",
      revision: "r1",
      quantity: "force",
      unit: "N",
      direction: "axial",
      range_min: 0,
      range_max: 500_000,
      calibration_version: "synthetic-cal1",
      calibration_at: "2026-01-01T00:00:00Z",
      calibration_valid_until: "2027-01-01T00:00:00Z",
      calibration_reference: "Synthetic test only",
      synchronization_source: "synthetic-clock",
    })
  ).json();
  async function force(value: number, observedAt: Date): Promise<{ id: string; value_kn: number }> {
    const content = Buffer.from(
      JSON.stringify({
        schema_version: "openvigil.direct-force.v1",
        tendon_id: tendon.id,
        sensor_id: forceSensor.id,
        observed_at: observedAt.toISOString(),
        unit: "N",
        value,
        calibration_version: forceSensor.calibration_version,
        uncertainty_kn: 0.25,
      }),
    );
    const artifact = await upload(request, "structural-records/uploads/presign", content, {
      turbine_id: "WT-023",
      file_name: "synthetic-force.json",
    });
    return (
      await command(request, "prestress-observations", {
        turbine_id: "WT-023",
        tendon_id: tendon.id,
        sensor_id: forceSensor.id,
        ...artifact,
        source_kind: "synthetic_test",
      })
    ).json() as Promise<{ id: string; value_kn: number }>;
  }
  const previous = await force(125_000, new Date(Date.now() - 172_800_000));
  const origin = await force(110_000, new Date(Date.now() - 86_400_000));
  expect(origin.value_kn).toBe(110);
  const documentId = "KB-STRUCTURAL-E2E";
  const quote = "Accept direct force from 120 kN to 130 kN for this synthetic test only.";
  const procedure = await upload(
    request,
    "knowledge/documents/uploads/presign",
    Buffer.from(`# Synthetic software procedure\n\n${quote}\n`),
    {
      document_id: documentId,
      file_name: "synthetic-procedure.md",
      content_type: "text/markdown",
    },
  );
  await command(
    request,
    "knowledge/documents",
    {
      document_id: documentId,
      title: "Synthetic structural software challenge procedure",
      document_type: "maintenance-procedure",
      document_version: "synthetic-r1",
      content_type: "text/markdown",
      ...procedure,
    },
    manager,
    202,
  );
  await expect
    .poll(
      async () =>
        pollRead(
          request,
          `knowledge/documents/${documentId}/passages`,
          (body) => body.passages.length,
          -1,
        ),
      { timeout: 60_000 },
    )
    .toBeGreaterThan(0);
  const passages = (await get(request, `knowledge/documents/${documentId}/passages`)).passages;
  const passage = passages.find((row: { text: string }) => row.text.includes(quote));
  expect(passage).toBeDefined();
  if (!passage) throw new Error("Actual indexed procedure does not contain its required quote");
  const created = await (
    await command(
      request,
      "structural-missions",
      {
        turbine_id: "WT-023",
        component_id: component.id,
        title: "Synthetic real-service force retest",
        scenario: "prestress_retest",
        source_id: origin.id,
        previous_prestress_id: previous.id,
        planning_duration_hours: 1,
        force_acceptance: {
          minimum_kn: 120,
          maximum_kn: 130,
          procedure: {
            kind: "knowledge_passage",
            source_id: passage.passage_id,
            relation: "supports",
            quote,
          },
        },
      },
      manager,
      202,
    )
  ).json();
  const missionId = created.mission_id;
  await expect
    .poll(
      async () =>
        pollRead(request, `missions/${missionId}`, (body) => body.status, "audit_unavailable"),
      { timeout: 90_000 },
    )
    .toBe("under_review");
  const mission = await get(request, `missions/${missionId}`);
  const claim = await get(
    request,
    `engineering-claims/${mission.public_state.engineering_claim_id}`,
  );
  const reviewed = await (
    await command(
      request,
      `engineering-claims/${claim.id}/review`,
      {
        action: "approve",
        expected_revision: claim.revision,
        reason: "Synthetic independent exact-source and calibration review",
      },
      reviewer,
      200,
    )
  ).json();
  expect(reviewed.authorizes_work).toBe(false);
  await page.setExtraHTTPHeaders(identity("business-approver"));
  await page.goto(`/missions/${missionId}`);
  await expect(page.getByRole("button", { name: "批准推荐方案" })).toBeVisible({ timeout: 20_000 });
  await page.getByLabel("审批原因").fill("Approve synthetic retest only; no operating permission");
  const approved = page.waitForResponse(
    (response) =>
      response.url().endsWith(api + `missions/${missionId}/approvals`) &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "批准推荐方案" }).dblclick();
  const approvalResponse = await approved;
  expect(approvalResponse.status(), await approvalResponse.text()).toBe(200);
  const approval = await approvalResponse.json();
  const approvalRequest = approvalResponse.request();
  const duplicate = await command(
    request,
    `missions/${missionId}/approvals`,
    approvalRequest.postDataJSON(),
    "business-approver",
    200,
    approvalRequest.headers()["idempotency-key"],
  );
  expect(duplicate.headers()["idempotency-replayed"]).toBe("true");
  expect((await duplicate.json()).work_order_id).toBe(approval.work_order_id);
  const orderId = approval.work_order_id;
  const order = await get(request, `structural-work-orders/${orderId}`);
  expect(order.tasks).toHaveLength(2);
  const retest = await force(125_000, new Date());
  const measurements = [
    {
      permit_reference: "Synthetic permit",
      isolation_reference: "Synthetic isolation",
      calibration_reference: "synthetic-cal1",
    },
    { retest_source_id: retest.id, measurement_reference: "Synthetic calibrated direct retest" },
  ];
  for (let index = 0; index < order.tasks.length; index++) {
    const task = order.tasks[index];
    const artifact = await upload(
      request,
      `work-orders/${orderId}/tasks/${task.id}/artifacts/presign`,
      Buffer.from(JSON.stringify(measurements[index])),
      { file_name: `synthetic-task-${index}.json`, content_type: "application/json" },
      "business-field",
    );
    const completedTask = await (
      await command(
        request,
        `work-orders/${orderId}/tasks/${task.id}/complete`,
        {
          result: "Synthetic actual object upload; field qualification unverified",
          ...artifact,
          measurement: measurements[index],
        },
        "business-field",
        200,
      )
    ).json();
    if (index === 1) {
      expect(completedTask.work_order_status).toBe("awaiting_health_review");
      expect(completedTask.workflow_finalized).toBe(false);
    }
  }
  const beforeReview = await get(request, `missions/${missionId}`);
  const healthBody = {
    expected_mission_revision: beforeReview.revision,
    action: "resolve_review",
    reason: "Synthetic independent retest review; no turbine operating permission",
    hypothesis_outcome: "not_supported",
  };
  const deniedHealth = await request.post(api + `structural-work-orders/${orderId}/health-review`, {
    headers: { ...identity("business-field"), "Idempotency-Key": randomUUID() },
    data: healthBody,
  });
  expect(deniedHealth.status()).toBe(403);
  const closed = await (
    await command(
      request,
      `structural-work-orders/${orderId}/health-review`,
      healthBody,
      reviewer,
      200,
    )
  ).json();
  expect(closed.case_review_status).toBe("pending");
  const caseId = closed.knowledge_case_id;
  await command(
    request,
    `structural-cases/${caseId}/review`,
    {
      expected_revision: 1,
      action: "approve",
      reason: "Synthetic independent case review preserving actual source and uncertainty",
    },
    "business-case-reviewer",
    200,
  );
  expect((await get(request, `missions/${missionId}`)).status).toBe("completed");
  expect((await get(request, `work-orders/${orderId}`)).status).toBe("completed");

  const modalClaim = await (
    await command(request, "engineering-claims", {
      turbine_id: "WT-023",
      mission_id: missionId,
      component_id: component.id,
      claim_kind: "screening_finding",
      conclusion: "Synthetic 0.5 Hz observation needs human review",
      applicability: { boundary: "Synthetic software challenge only" },
      evidence: [
        { kind: "modal", source_id: completed.modal_observations[0].id, relation: "supports" },
      ],
      valid_until: new Date(Date.now() + 86_400_000).toISOString(),
    })
  ).json();
  // This statement was authored by manager, unlike the workflow-generated claim.
  const selfReview = await request.post(api + `engineering-claims/${modalClaim.id}/review`, {
    headers: { ...identity(manager), "Idempotency-Key": randomUUID() },
    data: {
      action: "approve",
      expected_revision: modalClaim.revision,
      reason: "Synthetic own review must fail",
    },
  });
  expect(selfReview.status()).toBe(422);
  await command(
    request,
    `engineering-claims/${modalClaim.id}/review`,
    {
      action: "approve",
      expected_revision: modalClaim.revision,
      reason: "Synthetic exact modal source independently verified",
    },
    reviewer,
    200,
  );
  const graphPath = api + `knowledge-graph/entities/${modalClaim.id}/subgraph?depth=4`;
  await expect
    .poll(async () => (await request.get(graphPath, { headers: identity(manager) })).status(), {
      timeout: 90_000,
    })
    .toBe(200);
  const graph = await (await request.get(graphPath, { headers: identity(manager) })).json();
  expect(graph.meta.projectionBackend).toBe("neo4j");
  const statement = graph.data.nodes.find(
    (node: { type: string }) => node.type === "EngineeringClaim",
  );
  expect(statement.properties.authorizesWork).toBe(false);
  expect(statement.properties.recordSemantics).toBe("reviewed_engineering_statement");
  const originalProjection = (await get(request, "knowledge-graph/summary")).sourceRevision;
  // Mutate only this test-owned original object. No SQL/graph rebuild occurs.
  const tampered = await request.put(uploadedRequest.url(), {
    data: Buffer.from("{}"),
    headers: { "content-type": "application/json" },
  });
  expect(tampered.status()).toBe(200);
  expect((await request.get(graphPath, { headers: identity(manager) })).status()).toBe(404);
  const restored = await request.put(uploadedRequest.url(), {
    data: bytes,
    headers: { "content-type": "application/json" },
  });
  expect(restored.status()).toBe(200);
  const restoredGraph = await request.get(graphPath, { headers: identity(manager) });
  expect(restoredGraph.status()).toBe(200);
  expect((await get(request, "knowledge-graph/summary")).sourceRevision).toBe(originalProjection);
  const hiddenGraph = await request.get(graphPath, { headers: identity("business-restricted") });
  expect(hiddenGraph.status()).toBe(404);
  await page.setExtraHTTPHeaders(identity(manager));
  await page.goto("/knowledge-graph");
  await expect(page.getByRole("textbox", { name: "图谱实体 ID" })).toBeEnabled();
  await page.getByRole("textbox", { name: "图谱实体 ID" }).fill(modalClaim.id);
  let workspaceResponse = page.waitForResponse(
    (response) => new URL(response.url()).pathname === "/api/knowledge-graph",
    { timeout: 30_000 },
  );
  await page.getByRole("button", { name: "查询", exact: true }).click();
  let workspace = await workspaceResponse;
  for (let retry = 0; workspace.status() === 503 && retry < 3; retry++) {
    const rejected = await workspace.json();
    expect(Object.keys(rejected)).toEqual(["error"]);
    expect(rejected.error.code).toBe("READ_AUDIT_UNAVAILABLE");
    rejectedAuditReads.push("/api/knowledge-graph");
    await expect(page.getByRole("alert").filter({ hasText: "图谱服务不可用" })).toBeVisible();
    await expect(page.getByRole("note")).toHaveCount(0);
    workspaceResponse = page.waitForResponse(
      (response) => new URL(response.url()).pathname === "/api/knowledge-graph",
      { timeout: 30_000 },
    );
    await page.getByRole("button", { name: "刷新", exact: true }).click();
    workspace = await workspaceResponse;
  }
  expect(workspace.status(), await workspace.text()).toBe(200);
  await expect(page.getByRole("note")).toContainText("独立审核的工程结论 · 修订 2");
  await command(
    request,
    `engineering-claims/${modalClaim.id}/review`,
    {
      action: "withdraw",
      expected_revision: 2,
      reason: "Synthetic withdrawal must invalidate cached graph",
    },
    reviewer,
    200,
  );
  expect((await request.get(graphPath, { headers: identity(manager) })).status()).toBe(404);
  let withdrawalResponse = page.waitForResponse(
    (response) => new URL(response.url()).pathname === "/api/knowledge-graph",
    { timeout: 30_000 },
  );
  await page.getByRole("button", { name: "刷新", exact: true }).click();
  await expect(page.getByRole("note")).toHaveCount(0);
  let withdrawal = await withdrawalResponse;
  for (let retry = 0; withdrawal.status() === 503 && retry < 3; retry++) {
    const rejected = await withdrawal.json();
    expect(Object.keys(rejected)).toEqual(["error"]);
    expect(rejected.error.code).toBe("READ_AUDIT_UNAVAILABLE");
    rejectedAuditReads.push("/api/knowledge-graph?after=withdrawal");
    await expect(page.getByRole("alert").filter({ hasText: "图谱服务不可用" })).toBeVisible();
    await expect(page.getByRole("note")).toHaveCount(0);
    withdrawalResponse = page.waitForResponse(
      (response) => new URL(response.url()).pathname === "/api/knowledge-graph",
      { timeout: 30_000 },
    );
    await page.getByRole("button", { name: "刷新", exact: true }).click();
    withdrawal = await withdrawalResponse;
  }
  expect(withdrawal.status(), await withdrawal.text()).toBe(404);
  await expect(page.getByRole("alert").filter({ hasText: "图谱服务不可用" })).toBeVisible();
  await expect(page.getByRole("note")).toHaveCount(0);
  await expect(page.getByText(modalClaim.conclusion, { exact: true })).toHaveCount(0);
  const receipt = {
    mission_id: missionId,
    work_order_id: orderId,
    case_id: caseId,
    modal_claim_id: modalClaim.id,
    run_ids: [run.id, badRun.id],
    modal_ids: completed.modal_observations.map((mode: { id: string }) => mode.id),
    source_kind: "synthetic_test",
    storage: "actual_minio",
    graph: "actual_neo4j",
    algorithm: "actual_pyoma2_fdd",
    field_qualification: "unverified",
    audit_admission_rejections: rejectedAuditReads,
  };
  writeFileSync(process.env.WINDOPS_E2E_STRUCTURAL_RECEIPT!, JSON.stringify(receipt, null, 2));
  await testInfo.attach("structural-receipt", {
    contentType: "application/json",
    body: JSON.stringify(receipt),
  });
});
