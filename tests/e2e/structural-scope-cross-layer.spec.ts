import { randomUUID } from "node:crypto";
import { existsSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "@playwright/test";
import {
  fixtureIdentity,
  structuralApi,
  structuralCommand,
  structuralRead,
  structuralUpload,
} from "./structural-real-support";

if (
  process.env.WINDOPS_E2E_STRUCTURAL_SCOPE !== "1" ||
  process.env.WINDOPS_E2E_REAL_BACKEND !== "1"
) {
  throw new Error("Run the isolated business E2E runner with --scenario structural-scope");
}
const folder = process.env.WINDOPS_E2E_CHALLENGE_FOLDER;
if (!folder) throw new Error("Owned challenge folder is required");
const fixture = JSON.parse(readFileSync(join(folder, "scope-fixture.json"), "utf8")) as {
  components: { id: string }[];
  sensors: { id: string }[];
};
interface Graph {
  data: { nodes: { entityId: string; type: string; properties: Record<string, unknown> }[] };
  sourceRevision: string;
  meta: { projectionBackend: string };
}
interface Analysis {
  id: string;
  status: string;
  attempts: number;
  modal_observations: { id: string; frequency_hz: number }[];
}

test("real component and sensor scopes, mixed records, dependency denials and worker recovery", async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(540_000);
  const auditRejections: string[] = [];
  const denials: { subject: string; path: string; status: number }[] = [];
  const failures: { service: string; status: number; code: string; elapsedMs: number }[] = [];
  const read = <T>(path: string, subject?: string) =>
    structuralRead<T>(request, path, auditRejections, subject);
  const graphPath = (id: string) => `knowledge-graph/entities/${id}/subgraph?depth=4`;
  async function fault(service: string, action: string) {
    const id = randomUUID();
    const path = join(folder!, `fault-request-${id}.json`);
    writeFileSync(path + ".tmp", JSON.stringify({ id, service, action }));
    renameSync(path + ".tmp", path);
    const response = join(folder!, `fault-response-${id}.json`);
    await expect.poll(() => existsSync(response), { timeout: 30_000 }).toBe(true);
    expect(JSON.parse(readFileSync(response, "utf8"))).toEqual({
      id,
      service,
      action,
      status: "applied",
    });
  }
  async function denied(path: string, subject: string) {
    for (let attempt = 0; attempt < 4; attempt++) {
      const response = await request.get(structuralApi + path, {
        headers: fixtureIdentity(subject),
      });
      const body = await response.json();
      expect(Object.keys(body)).toEqual(["error"]);
      if (response.status() === 503) {
        expect(body.error.code).toBe("READ_AUDIT_UNAVAILABLE");
        auditRejections.push(path);
        continue;
      }
      expect(response.status(), JSON.stringify(body)).toBe(404);
      denials.push({ subject, path, status: response.status() });
      return;
    }
    throw new Error("Read admission did not recover for a scope denial");
  }
  async function projected(id: string): Promise<Graph> {
    await expect
      .poll(
        async () => {
          const response = await request.get(structuralApi + graphPath(id), {
            headers: fixtureIdentity(),
          });
          if (response.status() === 503) {
            const body = await response.json();
            expect(Object.keys(body)).toEqual(["error"]);
            expect(body.error.code).toBe("READ_AUDIT_UNAVAILABLE");
            auditRejections.push(graphPath(id));
            return 503;
          }
          expect([200, 404]).toContain(response.status());
          return response.status();
        },
        { timeout: 90_000 },
      )
      .toBe(200);
    return read<Graph>(graphPath(id));
  }
  async function waveform(channelIds: string[], offset: number) {
    const start = new Date(Date.now() - 86_400_000 + offset * 1000);
    const sampleCount = 4096,
      sampleRate = 16;
    const body = {
      schema_version: "openvigil.waveform.v1",
      turbine_id: "WT-023",
      started_at: start.toISOString(),
      sample_rate_hz: sampleRate,
      channels: channelIds.map((id, channel) => ({
        channel_id: id,
        unit: "m/s2",
        offset_seconds: 0,
        samples: Array.from(
          { length: sampleCount },
          (_, sample) => Math.sin((2 * Math.PI * 0.5 * sample) / sampleRate) * (1 + channel / 2),
        ),
      })),
    };
    const artifact = await structuralUpload(
      request,
      "structural-records/uploads/presign",
      Buffer.from(JSON.stringify(body)),
      {
        turbine_id: "WT-023",
        file_name: "synthetic-scope-waveform.json",
      },
    );
    return structuralCommand<{ id: string }>(request, "structural-records", {
      turbine_id: "WT-023",
      channel_ids: channelIds,
      started_at: start.toISOString(),
      ended_at: new Date(start.getTime() + (sampleCount / sampleRate) * 1000).toISOString(),
      sample_rate_hz: sampleRate,
      sample_count: sampleCount,
      ...artifact,
      source_kind: "synthetic_test",
      source_reference: "Explicit synthetic authorization challenge; no field data",
      environment: { operating_state: "stopped", rotor_speed_rpm: 0 },
    });
  }
  const own = await waveform(
    fixture.sensors.slice(0, 2).map((sensor) => sensor.id),
    0,
  );
  const recovery = await waveform(
    fixture.sensors.slice(0, 2).map((sensor) => sensor.id),
    3600,
  );
  const mixed = await waveform([fixture.sensors[0].id, fixture.sensors[2].id], 7200);
  const run = await structuralCommand<Analysis>(
    request,
    "structural-analyses",
    { record_id: own.id, config: {} },
    { status: 202 },
  );
  await expect
    .poll(async () => (await read<Analysis>(`structural-analyses/${run.id}`)).status, {
      timeout: 120_000,
    })
    .toBe("succeeded");
  const analyzed = await read<Analysis>(`structural-analyses/${run.id}`);
  expect(analyzed.modal_observations).toHaveLength(1);
  const context = await structuralCommand<{ mission_id: string; missing_evidence: string[] }>(
    request,
    "structural-missions",
    {
      turbine_id: "WT-023",
      component_id: fixture.components[0].id,
      title: "Synthetic scope and recovery software challenge",
      scenario: "modal_frequency_review",
      source_id: analyzed.modal_observations[0].id,
      planning_duration_hours: 1,
    },
    { status: 202 },
  );
  expect(context.missing_evidence).toContain("confirmed_environmental_baseline");
  interface Mission {
    status: string;
    public_state: { engineering_claim_id: string; diagnosis: { damage_probability: null } };
  }
  await expect
    .poll(async () => (await read<Mission>(`missions/${context.mission_id}`)).status, {
      timeout: 120_000,
    })
    .toBe("under_review");
  const mission = await read<Mission>(`missions/${context.mission_id}`);
  expect(mission.public_state.diagnosis.damage_probability).toBeNull();
  const claim = await read<{ id: string; revision: number }>(
    `engineering-claims/${mission.public_state.engineering_claim_id}`,
  );
  const approved = await structuralCommand<{ authorizes_work: boolean }>(
    request,
    `engineering-claims/${claim.id}/review`,
    {
      action: "approve",
      expected_revision: claim.revision,
      reason:
        "Independent source review for software recommendation only; absent baseline retained",
    },
    { subject: "business-reviewer", status: 200 },
  );
  expect(approved.authorizes_work).toBe(false);
  const before = await projected(claim.id);
  expect(before.meta.projectionBackend).toBe("neo4j");
  const statement = before.data.nodes.find((node) => node.entityId === claim.id)!;
  expect(statement.properties.authorizesWork).toBe(false);
  const componentGraph = await read<Graph>(
    graphPath(fixture.components[0].id),
    "business-component",
  );
  expect(componentGraph.data.nodes.map((node) => node.entityId)).toEqual([
    fixture.components[0].id,
  ]);
  const sensorGraph = await read<Graph>(graphPath(fixture.sensors[0].id), "business-sensor");
  expect(sensorGraph.data.nodes.map((node) => node.entityId)).toEqual([fixture.sensors[0].id]);
  for (const subject of ["business-component", "business-sensor"]) {
    for (const id of [
      fixture.components[1].id,
      fixture.sensors[2].id,
      own.id,
      mixed.id,
      run.id,
      analyzed.modal_observations[0].id,
      claim.id,
    ])
      await denied(graphPath(id), subject);
    await denied("structural-records?turbine_id=WT-023", subject);
    await denied(`structural-analyses/${run.id}`, subject);
    const command = await request.post(structuralApi + "structural-analyses", {
      headers: { ...fixtureIdentity(subject), "Idempotency-Key": randomUUID() },
      data: { record_id: mixed.id, config: {} },
    });
    expect(command.status(), await command.text()).toBe(404);
    expect(Object.keys(await command.json())).toEqual(["error"]);
  }
  await denied(graphPath(fixture.sensors[0].id), "business-component");
  await denied(graphPath(fixture.components[0].id), "business-sensor");
  await denied(graphPath(fixture.components[0].id), "business-restricted");
  await denied(graphPath(fixture.components[0].id), "business-knowledge-only");
  await page.setExtraHTTPHeaders(fixtureIdentity("business-component"));
  await page.goto("/knowledge-graph");
  const input = page.getByRole("textbox", { name: "图谱实体 ID" });
  await expect(input).toBeEnabled({ timeout: 20_000 });
  await input.fill(fixture.components[0].id);
  const queried = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/knowledge-graph" &&
      response.request().method() === "GET",
    { timeout: 30_000 },
  );
  await page.getByRole("button", { name: "查询", exact: true }).click();
  let queriedResponse = await queried;
  for (let retry = 0; queriedResponse.status() === 503 && retry < 3; retry++) {
    const rejected = await queriedResponse.json();
    expect(Object.keys(rejected)).toEqual(["error"]);
    expect(rejected.error.code).toBe("READ_AUDIT_UNAVAILABLE");
    auditRejections.push("/api/knowledge-graph");
    await expect(page.getByRole("alert").filter({ hasText: "图谱服务不可用" })).toBeVisible();
    const retried = page.waitForResponse(
      (response) => new URL(response.url()).pathname === "/api/knowledge-graph",
      { timeout: 30_000 },
    );
    await page
      .getByRole("alert")
      .filter({ hasText: "图谱服务不可用" })
      .getByRole("button", { name: "重试", exact: true })
      .click();
    queriedResponse = await retried;
  }
  expect(queriedResponse.status(), await queriedResponse.text()).toBe(200);
  const workspace = await queriedResponse.json();
  expect(workspace.data.graph.nodes.map((node: { entityId: string }) => node.entityId)).toEqual([
    fixture.components[0].id,
  ]);
  await expect(page.getByText(fixture.components[0].id, { exact: true }).first()).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("real-component-scope.png"), fullPage: true });
  for (const service of ["minio", "neo4j", "redis"]) {
    await fault(service, "pause");
    try {
      const started = Date.now();
      const response = await request.get(structuralApi + graphPath(claim.id), {
        headers: fixtureIdentity(),
        timeout: 30_000,
      });
      const body = await response.json();
      const code = body.error.code as string;
      expect(response.status()).toBe(503);
      if (service === "neo4j" && code === "BACKEND_TIMEOUT") {
        expect(body).toEqual({
          data: null,
          error: {
            code: "BACKEND_TIMEOUT",
            message: "The production backend did not respond before the configured deadline.",
          },
          meta: { runtimeMode: "production", fixtureFallback: false },
        });
      } else {
        expect(Object.keys(body)).toEqual(["error"]);
        expect(code).toBe(
          service === "redis" ? "READ_AUDIT_UNAVAILABLE" : "KNOWLEDGE_GRAPH_UNAVAILABLE",
        );
      }
      expect(Date.now() - started).toBeLessThan(22_000);
      failures.push({ service, status: response.status(), code, elapsedMs: Date.now() - started });
    } finally {
      await fault(service, "unpause");
    }
    const restored = await projected(claim.id);
    expect(restored.sourceRevision).toBe(before.sourceRevision);
    expect(
      restored.data.nodes.find((node) => node.entityId === claim.id)?.properties.readIdentity,
    ).toBe(statement.properties.readIdentity);
  }
  await fault("structural-worker", "stop");
  const key = randomUUID();
  const queued = await structuralCommand<Analysis>(
    request,
    "structural-analyses",
    { record_id: recovery.id, config: {} },
    { status: 202, key },
  );
  expect(queued.status).toBe("pending");
  await new Promise((resolve) => setTimeout(resolve, 2000));
  expect((await read<Analysis>(`structural-analyses/${queued.id}`)).status).toBe("pending");
  const replay = await request.post(structuralApi + "structural-analyses", {
    headers: { ...fixtureIdentity(), "Idempotency-Key": key },
    data: { record_id: recovery.id, config: {} },
  });
  expect(replay.status()).toBe(202);
  expect(replay.headers()["idempotency-replayed"]).toBe("true");
  expect((await replay.json()).id).toBe(queued.id);
  await fault("structural-worker", "start");
  await expect
    .poll(async () => (await read<Analysis>(`structural-analyses/${queued.id}`)).status, {
      timeout: 120_000,
    })
    .toBe("succeeded");
  const recovered = await read<Analysis>(`structural-analyses/${queued.id}`);
  expect(recovered.attempts).toBe(1);
  expect(recovered.modal_observations).toHaveLength(1);
  expect(recovered.modal_observations[0].frequency_hz).toBeCloseTo(0.5, 3);
  await projected(queued.id);
  await expect
    .poll(
      async () => {
        const projectedRun = await read<Graph>(graphPath(queued.id));
        return projectedRun.data.nodes.find((node) => node.entityId === queued.id)?.properties
          .status;
      },
      { timeout: 90_000 },
    )
    .toBe("succeeded");
  const receipt = {
    boundary: "Synthetic software scope and recovery; no field or release qualification",
    scenario: "structural_scope_recovery",
    component_ids: fixture.components.map((row) => row.id),
    sensor_ids: fixture.sensors.map((row) => row.id),
    record_ids: [own.id, recovery.id, mixed.id],
    mixed_record_id: mixed.id,
    run_ids: [run.id, queued.id],
    claim_id: claim.id,
    denials,
    failures,
    audit_rejections: auditRejections,
    pending_without_worker: true,
    replayed_same_run: true,
    recovered_attempts: recovered.attempts,
  };
  const target = process.env.WINDOPS_E2E_STRUCTURAL_RECEIPT;
  if (!target) throw new Error("Structural receipt path is required");
  writeFileSync(target, JSON.stringify(receipt, null, 2));
  await testInfo.attach("structural-scope-recovery", {
    body: JSON.stringify(receipt),
    contentType: "application/json",
  });
});
