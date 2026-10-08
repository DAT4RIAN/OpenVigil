import { createHash, randomUUID } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { expect, test, type Response, type APIRequestContext } from "@playwright/test";
import { fixtureIdentity, structuralCommand, structuralUpload } from "./structural-real-support";

if (process.env.WINDOPS_E2E_DOCUMENT !== "1" || process.env.WINDOPS_E2E_REAL_BACKEND !== "1") {
  throw new Error(
    "Run isolated business acceptance with --scenario document and explicit parser inputs",
  );
}

interface DocumentRow {
  document_id: string;
  ingestion_status: string;
  vectorized: boolean;
  artifact_sha256: string;
  parse_state: { status: string; attempts: number };
}
interface PassageRow {
  passage_id: string;
  document_id: string;
  text: string;
  page_number: number;
  source_sha256: string;
  native_locator: { requires_numeric_review: boolean; regions: unknown[]; table_cell?: unknown };
}

// Keep every known fail-closed read denial, require a real 200 within four
// attempts, and reject all other response shapes/codes. No source data is
// accepted from a gateway timeout or unavailable audit sink.
async function documentRead<T>(
  request: APIRequestContext,
  path: string,
  denials: string[],
): Promise<T> {
  for (let attempt = 0; attempt < 4; attempt++) {
    const response = await request.get("/api/backend/" + path, { headers: fixtureIdentity() });
    if (response.status() === 503) {
      const body = await response.json();
      if (body.error?.code === "READ_AUDIT_UNAVAILABLE") {
        expect(Object.keys(body)).toEqual(["error"]);
      } else {
        expect(body.error?.code).toBe("BACKEND_TIMEOUT");
        expect(Object.keys(body).sort()).toEqual(["data", "error", "meta"]);
        expect(body.data).toBeNull();
        expect(body.meta).toEqual({ runtimeMode: "production", fixtureFallback: false });
      }
      denials.push(`${path}:${body.error.code}`);
      continue;
    }
    expect(response.status(), await response.text()).toBe(200);
    return response.json() as Promise<T>;
  }
  throw new Error(`Actual document read did not recover within four attempts: ${path}`);
}

test("real scanned PDF queue publishes indexed source regions; failed input remains empty", async ({
  page,
  context,
  request,
}) => {
  test.setTimeout(420_000);
  const rejectedAuditReads: string[] = [];
  const fixture = process.env.WINDOPS_E2E_DOCUMENT_FIXTURE!;
  const content = readFileSync(fixture);
  const artifactSha = createHash("sha256").update(content).digest("hex");
  const capabilities = await documentRead<{
    docling_pdf_configured: boolean;
    worker_health_verified: boolean;
  }>(request, "knowledge/parser-capabilities", rejectedAuditReads);
  expect(capabilities.docling_pdf_configured).toBe(true);
  expect(capabilities.worker_health_verified).toBe(false);
  const browserConfigurationRejections: Response[] = [];
  page.on("response", (response) => {
    if (
      new URL(response.url()).pathname === "/api/backend/knowledge/parser-capabilities" &&
      response.status() >= 400
    )
      browserConfigurationRejections.push(response);
  });
  await context.setExtraHTTPHeaders(fixtureIdentity());
  await page.goto("/knowledge");
  const checkbox = page.getByRole("checkbox", { name: "PDF 扫描件解析" });
  const retryConfiguration = page.getByRole("button", { name: "重试解析配置" });
  for (let attempt = 0; attempt < 3; attempt++) {
    await expect
      .poll(
        async () =>
          (await checkbox.isEnabled()) ||
          ((await retryConfiguration.count()) > 0 && (await retryConfiguration.isEnabled())),
        { timeout: 30_000 },
      )
      .toBe(true);
    if (await checkbox.isEnabled()) break;
    await retryConfiguration.click();
  }
  await expect(checkbox).toBeEnabled({ timeout: 30_000 });
  await checkbox.check();
  const registered = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/backend/knowledge/documents",
    { timeout: 120_000 },
  );
  const grantResponse = () =>
    page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === "/api/backend/knowledge/documents/uploads/presign",
    );
  const initialGrant = grantResponse();
  await page.locator('input[type="file"]').setInputFiles(fixture);
  let grant = await initialGrant;
  const grantPayload = grant.request().postDataJSON();
  const grantKey = grant.request().headers()["idempotency-key"];
  const ambiguousGrantResponses: number[] = [];
  for (let attempt = 0; grant.status() === 503 && attempt < 3; attempt++) {
    const failure = await grant.json();
    expect(failure.error.code).toBe("BACKEND_TIMEOUT");
    ambiguousGrantResponses.push(grant.status());
    const next = grantResponse();
    const reconcile = page.getByRole("button", { name: "核验同一提交" });
    await expect(reconcile).toBeEnabled();
    await reconcile.click();
    grant = await next;
    expect(grant.request().postDataJSON()).toEqual(grantPayload);
    expect(grant.request().headers()["idempotency-key"]).toBe(grantKey);
  }
  expect(grant.status(), await grant.text()).toBe(200);
  const registration = await registered;
  expect(registration.status(), await registration.text()).toBe(202);
  const initial: DocumentRow = await registration.json();
  expect(initial.ingestion_status).toBe("pending_parse");
  expect(initial.vectorized).toBe(false);
  expect(initial.artifact_sha256).toBe(artifactSha);
  const payload = registration.request().postDataJSON();
  const key = registration.request().headers()["idempotency-key"];
  const pending = await documentRead<{ passages: PassageRow[] }>(
    request,
    `knowledge/documents/${initial.document_id}/passages`,
    rejectedAuditReads,
  );
  expect(pending.passages).toEqual([]);
  await expect
    .poll(
      async () => {
        const result = await documentRead<{ documents: DocumentRow[] }>(
          request,
          "knowledge/documents",
          rejectedAuditReads,
        );
        return result.documents.find((row) => row.document_id === initial.document_id)
          ?.ingestion_status;
      },
      { timeout: 180_000, intervals: [1000, 2000] },
    )
    .toBe("indexed");
  const replay = await request.post("/api/backend/knowledge/documents", {
    data: payload,
    headers: { ...fixtureIdentity(), "Idempotency-Key": key },
  });
  expect(replay.status(), await replay.text()).toBe(202);
  expect(replay.headers()["idempotency-replayed"]).toBe("true");
  const secondKey = await structuralCommand<DocumentRow>(request, "knowledge/documents", payload, {
    status: 202,
  });
  expect(secondKey.document_id).toBe(initial.document_id);
  const result = await documentRead<{ passages: PassageRow[] }>(
    request,
    `knowledge/documents/${initial.document_id}/passages?limit=100`,
    rejectedAuditReads,
  );
  expect(result.passages).toHaveLength(15);
  expect(result.passages.filter((row) => row.native_locator.table_cell)).toHaveLength(9);
  expect(
    result.passages.every(
      (row) =>
        row.page_number === 2 &&
        row.source_sha256 === artifactSha &&
        row.native_locator.requires_numeric_review &&
        row.native_locator.regions.length > 0,
    ),
  ).toBe(true);
  for (const text of ["混塔预应力复测记录", "+123.45 kN", "-0.25 mm", "WT-023", "118.20"]) {
    expect(result.passages.map((row) => row.text).join("\n")).toContain(text);
  }
  await page.goto(`/knowledge?document=${initial.document_id}`);
  const drawer = page.getByRole("dialog");
  await expect(drawer.getByText("已索引", { exact: true })).toBeVisible();
  await expect(drawer.getByRole("img", { name: "页面区域示意" }).first()).toBeVisible();
  await expect(drawer.getByText(/数字、正负号、小数点和单位/).first()).toBeVisible();
  const source = await documentRead<{
    download_url: string;
    artifact_sha256: string;
    page_number: number;
  }>(
    request,
    `knowledge/documents/${initial.document_id}/source?passage_id=${result.passages[0].passage_id}`,
    rejectedAuditReads,
  );
  expect(source.page_number).toBe(2);
  const original = await request.get(source.download_url);
  expect(original.status()).toBe(200);
  expect(
    createHash("sha256")
      .update(await original.body())
      .digest("hex"),
  ).toBe(artifactSha);
  for (const path of [
    `knowledge/documents/${initial.document_id}/passages`,
    `knowledge/documents/${initial.document_id}/source`,
    `knowledge/passages/${result.passages[0].passage_id}`,
  ]) {
    const denied = await request.get("/api/backend/" + path, {
      headers: fixtureIdentity("business-restricted"),
    });
    expect(denied.status(), await denied.text()).toBe(404);
  }
  const badId = `KD-bad-${randomUUID()}`;
  const badArtifact = await structuralUpload(
    request,
    "knowledge/documents/uploads/presign",
    Buffer.from("%PDF-invalid"),
    {
      document_id: badId,
      content_type: "application/pdf",
      file_name: "declared-invalid-fixture.pdf",
    },
  );
  await structuralCommand(
    request,
    "knowledge/documents",
    {
      document_id: badId,
      title: "Declared unusable PDF fixture",
      document_type: "maintenance-procedure",
      document_version: "1",
      content_type: "application/pdf",
      parser: "docling",
      ...badArtifact,
    },
    { status: 202 },
  );
  await expect
    .poll(
      async () => {
        const rows = await documentRead<{ documents: DocumentRow[] }>(
          request,
          "knowledge/documents",
          rejectedAuditReads,
        );
        return rows.documents.find((row) => row.document_id === badId)?.ingestion_status;
      },
      { timeout: 150_000, intervals: [1000, 2000] },
    )
    .toBe("parse_failed");
  const failedPassages = await documentRead<{ passages: PassageRow[] }>(
    request,
    `knowledge/documents/${badId}/passages`,
    rejectedAuditReads,
  );
  expect(failedPassages.passages).toEqual([]);
  await page.screenshot({
    path: process.env.WINDOPS_E2E_DOCUMENT_RECEIPT!.replace(".json", ".png"),
    fullPage: true,
  });
  const configurationRejections: string[] = [];
  for (const rejected of browserConfigurationRejections) {
    expect(rejected.status()).toBe(503);
    const error = await rejected.json();
    expect(["BACKEND_TIMEOUT", "READ_AUDIT_UNAVAILABLE"]).toContain(error.error.code);
    configurationRejections.push(error.error.code);
  }
  writeFileSync(
    process.env.WINDOPS_E2E_DOCUMENT_RECEIPT!,
    JSON.stringify(
      {
        schema: "openvigil.document-browser.v1",
        document_id: initial.document_id,
        failed_document_id: badId,
        artifact_sha256: artifactSha,
        passage_ids: result.passages.map((row) => row.passage_id),
        source_verified: true,
        numeric_fixture_checked: true,
        rejected_audit_reads: rejectedAuditReads,
        ambiguous_grant_responses: ambiguousGrantResponses,
        configuration_rejections: configurationRejections,
        boundary:
          "Real OCR/PG/Redis/MinIO/Neo4j; synthetic scan and identity, deterministic embeddings; no field qualification",
      },
      null,
      2,
    ),
  );
});
