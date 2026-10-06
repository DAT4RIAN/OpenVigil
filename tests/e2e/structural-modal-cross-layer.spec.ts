import { randomUUID } from "node:crypto";
import { writeFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import {
  fixtureIdentity,
  structuralApi,
  structuralCommand,
  structuralRead,
  structuralUpload,
} from "./structural-real-support";

if (
  process.env.WINDOPS_E2E_STRUCTURAL_MODAL !== "1" ||
  process.env.WINDOPS_E2E_REAL_BACKEND !== "1"
) {
  throw new Error("Run the isolated business E2E runner with --scenario structural-modal");
}

type Identified = { id: string };
type Modal = Identified & { frequency_hz: number };
type Analysis = Identified & {
  status: string;
  result: { quality: { usable: boolean }; source_kind: string };
  modal_observations: Modal[];
};
type Mission = Identified & {
  revision: number;
  status: string;
  public_state: { engineering_claim_id: string };
};
type Baseline = Identified & {
  source_kind: string;
  model: { validation: { training_count: number; validation_count: number } };
};
type Order = {
  work_order: Identified & { created_at: string };
  tasks: Identified[];
};
type HealthReview = {
  knowledge_case_id: string;
  case_review_status: string;
  work_order_status: string;
  review: {
    assessment: {
      eligible_to_resolve_review: boolean;
      exclusions: string[];
      comparison: { status: string; mode_mac: number; damage_probability: null };
      field_qualification: string;
      authorizes_operation: boolean;
      evidence_card: { source: { sha256: string } };
    };
  };
};

test("real queued 30-window baseline and complete post-work modal closure", async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(1_080_000);
  const rejectedAudits: string[] = [];
  const read = <T>(path: string) => structuralRead<T>(request, path, rejectedAudits);
  const component = await structuralCommand<Identified>(request, "tower-components", {
    turbine_id: "WT-023",
    code: "SYNTHETIC-MODAL-C1",
    name: "软件模态挑战段",
    component_type: "concrete_segment",
    revision: "r1",
    design_reference: "Synthetic software challenge, no OEM or site qualification",
  });
  const sensors: Identified[] = [];
  for (let index = 0; index < 2; index++) {
    sensors.push(
      await structuralCommand<Identified>(request, "sensor-channels", {
        turbine_id: "WT-023",
        component_id: component.id,
        code: `SYNTHETIC-MODAL-A${index}`,
        revision: "r1",
        quantity: "acceleration",
        unit: "m/s2",
        direction: "X",
        range_min: -10,
        range_max: 10,
        calibration_version: "synthetic-modal-cal1",
        calibration_at: "2026-01-01T00:00:00Z",
        calibration_valid_until: "2027-01-01T00:00:00Z",
        calibration_reference: "Synthetic calibration, not field certification",
        synchronization_source: "synthetic-clock",
      }),
    );
  }
  const runIds: string[] = [];
  const allModes: string[] = [];
  const sampleRate = 16;
  const sampleCount = 4096;
  const durationMs = (sampleCount / sampleRate) * 1000;
  async function waveform(start: Date, frequency: number, temperature: number) {
    const body = {
      schema_version: "openvigil.waveform.v1",
      turbine_id: "WT-023",
      started_at: start.toISOString(),
      sample_rate_hz: sampleRate,
      channels: sensors.map((sensor, channel) => ({
        channel_id: sensor.id,
        unit: "m/s2",
        offset_seconds: 0,
        samples: Array.from(
          { length: sampleCount },
          (_, sample) =>
            Math.sin((2 * Math.PI * frequency * sample) / sampleRate) * (1 + channel / 2),
        ),
      })),
    };
    const artifact = await structuralUpload(
      request,
      "structural-records/uploads/presign",
      Buffer.from(JSON.stringify(body)),
      { turbine_id: "WT-023", file_name: "synthetic-modal.json" },
    );
    const record = await structuralCommand<Identified>(request, "structural-records", {
      turbine_id: "WT-023",
      channel_ids: sensors.map((sensor) => sensor.id),
      started_at: start.toISOString(),
      ended_at: new Date(start.getTime() + durationMs).toISOString(),
      sample_rate_hz: sampleRate,
      sample_count: sampleCount,
      ...artifact,
      source_kind: "synthetic_test",
      source_reference: "Independent synthetic software window; no field qualification",
      environment: { operating_state: "stopped", rotor_speed_rpm: 0, temperature_c: temperature },
    });
    const queued = await structuralCommand<Analysis>(
      request,
      "structural-analyses",
      { record_id: record.id, config: {} },
      { status: 202 },
    );
    expect(queued.status).toBe("pending");
    runIds.push(queued.id);
    await expect
      .poll(async () => (await read<Analysis>(`structural-analyses/${queued.id}`)).status, {
        timeout: 120_000,
      })
      .toBe("succeeded");
    const result = await read<Analysis>(`structural-analyses/${queued.id}`);
    expect(result.result.quality.usable).toBe(true);
    expect(result.result.source_kind).toBe("synthetic_test");
    expect(result.modal_observations).toHaveLength(1);
    expect(Math.abs(result.modal_observations[0].frequency_hz - frequency)).toBeLessThanOrEqual(
      sampleRate / 1024,
    );
    allModes.push(result.modal_observations[0].id);
    return { modal: result.modal_observations[0], ...artifact };
  }
  const now = Date.now();
  const training: string[] = [];
  for (let index = 0; index < 30; index++) {
    const window = await waveform(
      new Date(now - 3 * 86_400_000 + index * 3_600_000),
      0.5,
      index % 10,
    );
    training.push(window.modal.id);
  }
  const baseline = await structuralCommand<Baseline>(request, "health-baselines", {
    turbine_id: "WT-023",
    component_id: component.id,
    code: "synthetic-service-modal-baseline",
    revision: "synthetic-r1",
    confirmation_reference: "Synthetic healthy software windows; no field qualification",
    reference_modal_id: training[0],
    training_modal_ids: training,
    features: ["temperature_c"],
    valid_until: new Date(now + 30 * 86_400_000).toISOString(),
  });
  expect(baseline.source_kind).toBe("synthetic_test");
  expect(baseline.model.validation).toMatchObject({ training_count: 24, validation_count: 6 });
  const origin = await waveform(new Date(now - 86_400_000), 0.45, 5);
  const context = await structuralCommand<{
    mission_id: string;
    missing_evidence: string[];
    comparison: { status: string; damage_probability: null };
  }>(
    request,
    "structural-missions",
    {
      turbine_id: "WT-023",
      component_id: component.id,
      title: "Synthetic real-service modal frequency retest",
      scenario: "modal_frequency_review",
      source_id: origin.modal.id,
      baseline_id: baseline.id,
      planning_duration_hours: 1,
    },
    { status: 202 },
  );
  expect(context.missing_evidence).toEqual([]);
  expect(context.comparison).toMatchObject({ status: "requires_review", damage_probability: null });
  await expect
    .poll(async () => (await read<Mission>(`missions/${context.mission_id}`)).status, {
      timeout: 120_000,
    })
    .toBe("under_review");
  const mission = await read<Mission>(`missions/${context.mission_id}`);
  const claim = await read<Identified & { revision: number }>(
    `engineering-claims/${mission.public_state.engineering_claim_id}`,
  );
  await structuralCommand(
    request,
    `engineering-claims/${claim.id}/review`,
    {
      action: "approve",
      expected_revision: claim.revision,
      reason: "Independent synthetic modal source review, no operating authority",
    },
    { subject: "business-reviewer", status: 200 },
  );
  await page.setExtraHTTPHeaders(fixtureIdentity("business-approver"));
  await page.goto(`/missions/${context.mission_id}`);
  await expect(page.getByRole("button", { name: "批准推荐方案" })).toBeVisible({ timeout: 20_000 });
  await page.getByLabel("审批原因").fill("Approve synthetic modal retest only");
  const approvalResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname ===
        structuralApi + `missions/${context.mission_id}/approvals` &&
      response.request().method() === "POST",
    { timeout: 30_000 },
  );
  await page.getByRole("button", { name: "批准推荐方案" }).click();
  const approved = await approvalResponse;
  expect(approved.status(), await approved.text()).toBe(200);
  const { work_order_id: orderId } = (await approved.json()) as { work_order_id: string };
  const order = await read<Order>(`structural-work-orders/${orderId}`);
  expect(order.tasks).toHaveLength(2);
  const permit = {
    permit_reference: "Synthetic permit",
    isolation_reference: "Synthetic isolation",
    calibration_reference: "synthetic-modal-cal1",
  };
  const permitArtifact = await structuralUpload(
    request,
    `work-orders/${orderId}/tasks/${order.tasks[0].id}/artifacts/presign`,
    Buffer.from(JSON.stringify(permit)),
    { file_name: "synthetic-permit.json", content_type: "application/json" },
    "business-field",
  );
  await structuralCommand(
    request,
    `work-orders/${orderId}/tasks/${order.tasks[0].id}/complete`,
    { result: "Synthetic prerequisite verified", ...permitArtifact, measurement: permit },
    { subject: "business-field", status: 200 },
  );

  // The production clock and time gate are unchanged. The synthetic window is
  // staged now, but field handoff must wait until its actual end-exclusive end.
  const retestStart = new Date(Date.now() + 1000);
  expect(retestStart.getTime()).toBeGreaterThan(new Date(order.work_order.created_at).getTime());
  const retest = await waveform(retestStart, 0.5, 5);
  const measurement = {
    retest_source_id: retest.modal.id,
    measurement_reference: "Actual FDD of complete synthetic post-work window",
  };
  const measurementArtifact = await structuralUpload(
    request,
    `work-orders/${orderId}/tasks/${order.tasks[1].id}/artifacts/presign`,
    Buffer.from(JSON.stringify(measurement)),
    { file_name: "synthetic-modal-handoff.json", content_type: "application/json" },
    "business-field",
  );
  const completionBody = {
    result: "Synthetic actual modal retest",
    ...measurementArtifact,
    measurement,
  };
  const premature = await request.post(
    structuralApi + `work-orders/${orderId}/tasks/${order.tasks[1].id}/complete`,
    {
      headers: { ...fixtureIdentity("business-field"), "Idempotency-Key": randomUUID() },
      data: completionBody,
    },
  );
  expect(premature.status(), await premature.text()).toBe(422);
  expect(await premature.text()).toContain("future dated");
  const end = retestStart.getTime() + durationMs;
  await expect
    .poll(() => Date.now() >= end, { timeout: durationMs + 10_000, intervals: [1000] })
    .toBe(true);
  const handed = await structuralCommand<{
    workflow_finalized: boolean;
    work_order_status: string;
  }>(request, `work-orders/${orderId}/tasks/${order.tasks[1].id}/complete`, completionBody, {
    subject: "business-field",
    status: 200,
  });
  expect(handed).toMatchObject({
    workflow_finalized: false,
    work_order_status: "awaiting_health_review",
  });
  const current = await read<Mission>(`missions/${context.mission_id}`);
  const closed = await structuralCommand<HealthReview>(
    request,
    `structural-work-orders/${orderId}/health-review`,
    {
      expected_mission_revision: current.revision,
      action: "resolve_review",
      reason: "Independent actual FDD and confirmed synthetic baseline review",
      hypothesis_outcome: "not_supported",
    },
    { subject: "business-reviewer", status: 200 },
  );
  expect(closed.work_order_status).toBe("completed");
  expect(closed.case_review_status).toBe("pending");
  expect(closed.review.assessment).toMatchObject({
    eligible_to_resolve_review: true,
    exclusions: [],
    field_qualification: "unverified",
    authorizes_operation: false,
    comparison: { status: "within_screening_range", damage_probability: null },
  });
  expect(closed.review.assessment.comparison.mode_mac).toBeGreaterThanOrEqual(0.9);
  expect(closed.review.assessment.evidence_card.source.sha256).toBe(retest.artifact_sha256);
  await structuralCommand(
    request,
    `structural-cases/${closed.knowledge_case_id}/review`,
    {
      expected_revision: 1,
      action: "approve",
      reason: "Independent synthetic modal case source review",
    },
    { subject: "business-case-reviewer", status: 200 },
  );
  expect((await read<Mission>(`missions/${context.mission_id}`)).status).toBe("completed");
  expect(await read<Baseline>(`health-baselines/${baseline.id}`)).toEqual(baseline);
  const receipt = {
    scenario: "modal_frequency_review",
    mission_id: context.mission_id,
    work_order_id: orderId,
    case_id: closed.knowledge_case_id,
    claim_id: claim.id,
    baseline_id: baseline.id,
    training_modal_ids: training,
    modal_ids: allModes,
    run_ids: runIds,
    source_kind: "synthetic_test",
    field_qualification: "unverified",
    acquisition_clock: "actual_wall_time",
    postwork_window: { start: retestStart.toISOString(), end: new Date(end).toISOString() },
    audit_admission_rejections: rejectedAudits,
  };
  writeFileSync(process.env.WINDOPS_E2E_STRUCTURAL_RECEIPT!, JSON.stringify(receipt, null, 2));
  await testInfo.attach("modal-service-receipt", {
    contentType: "application/json",
    body: JSON.stringify(receipt),
  });
});
