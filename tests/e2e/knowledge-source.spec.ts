import { expect, test } from "@playwright/test";
import { createHash } from "node:crypto";

const documentId = "KB-NATIVE-UI-FIXTURE";
const passageId = "12345678-1234-4234-8234-123456789012";
const rawSource = "# Synthetic retest\nVerify calibration.\nRecord direct force.\n";
const document = {
  id: documentId,
  title: "原生位置界面测试资料",
  type: "maintenance-procedure",
  equipment: "UI fixture only",
  manufacturer: null,
  version: "synthetic-r1",
  updatedAt: "2026-10-05T00:00:00Z",
  vectorized: true,
  pageCount: null,
  language: "zh-CN",
  tags: ["UI fixture"],
  summary: "Synthetic browser interaction source",
  relatedTurbineIds: [],
  relatedMissionIds: [],
  ingestionStatus: "indexed",
};
const passage = {
  passage_id: passageId,
  document_id: documentId,
  document_version: "synthetic-r1",
  ordinal: 0,
  page_number: null,
  section: "Synthetic retest",
  text: "Verify calibration.\nRecord direct force.",
  source_sha256: "a".repeat(64),
  text_sha256: "b".repeat(64),
  native_locator: { kind: "text_lines", line_start: 2, line_end: 3, source_verified: true },
};

test.beforeEach(async ({ context, page }) => {
  await context.setExtraHTTPHeaders({
    "oai-authenticated-user-id": "user-manager",
    "oai-authenticated-user-email": "manager@example.com",
    "x-e2e-runtime": "production",
  });
  // This suite verifies browser interaction against explicit UI fixtures.
  // It is separate from database/object-store or site acceptance.
  await page.route("**/api/backend/knowledge/parser-capabilities", (route) =>
    route.fulfill({
      json: { docling_pdf_configured: true, max_artifact_bytes: 52428800, fixture: true },
    }),
  );
  await page.route("**/api/knowledge-documents*", (route) =>
    route.fulfill({
      json: {
        ok: true,
        data: { documents: [document] },
        meta: { fixture: true },
        error: null,
      },
    }),
  );
  await page.route(`**/api/backend/knowledge/documents/${documentId}/passages*`, (route) =>
    route.fulfill({
      json: {
        passages: [passage],
        next_cursor: null,
        fixture: true,
      },
    }),
  );
  await page.route(`**/api/backend/knowledge/passages/${passageId}`, (route) =>
    route.fulfill({ json: { ...passage, fixture: true } }),
  );
  await context.route("**/__e2e/native-source.txt*", (route) =>
    route.fulfill({ body: rawSource, contentType: "text/plain" }),
  );
});

test("native citation drawer reads actual text positions and opens a short source link", async ({
  page,
}) => {
  await page.route(`**/api/backend/knowledge/documents/${documentId}/source*`, (route) =>
    route.fulfill({
      json: {
        download_url: new URL("/__e2e/native-source.txt", route.request().url()).href,
        expires_at: new Date(Date.now() + 300_000).toISOString(),
        artifact_sha256: passage.source_sha256,
        document_version: "synthetic-r1",
        page_number: null,
        fixture: true,
      },
    }),
  );
  await page.goto(`/knowledge?document=${documentId}&passage=${passageId}`);
  const drawer = page.getByRole("dialog", { name: `${document.title} 文档详情` });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText("第 2–3 行 · 当前引用", { exact: true })).toBeVisible();
  await expect(drawer.getByText(passage.text, { exact: true })).toBeVisible();
  await expect(drawer.getByText("已索引", { exact: true })).toBeVisible();
  await expect(drawer.getByText(/文档预览|演示检索目录|第 1 页/)).toHaveCount(0);
  await drawer.getByRole("button", { name: "获取原文链接" }).last().click();
  await expect(drawer.getByRole("link", { name: "打开原文件" })).toBeVisible();
  const popupEvent = page.waitForEvent("popup");
  await drawer.getByRole("link", { name: "打开原文件" }).click();
  const popup = await popupEvent;
  await expect(popup.locator("body")).toContainText("Verify calibration.");
  await popup.close();
  await page.screenshot({
    path: ".artifacts/hybrid-tower-20261005/native-source-drawer.png",
    fullPage: true,
  });
});

test("source failure remains visible and retry obtains a new grant", async ({ page }) => {
  let calls = 0;
  await page.route(`**/api/backend/knowledge/documents/${documentId}/source*`, (route) => {
    calls += 1;
    return calls === 1
      ? route.fulfill({
          status: 422,
          json: { error: { code: "INVALID_TRANSITION", message: "Source SHA-256 mismatch" } },
        })
      : route.fulfill({
          json: {
            download_url: new URL("/__e2e/native-source.txt", route.request().url()).href,
            expires_at: new Date(Date.now() + 300_000).toISOString(),
            artifact_sha256: passage.source_sha256,
            document_version: "synthetic-r1",
            page_number: null,
            fixture: true,
          },
        });
  });
  await page.goto(`/knowledge?document=${documentId}`);
  const drawer = page.getByRole("dialog", { name: `${document.title} 文档详情` });
  await expect(drawer.getByText(passage.text, { exact: true })).toBeVisible();
  await drawer.getByRole("button", { name: "获取原文链接" }).first().click();
  await expect(drawer.getByRole("alert")).toContainText("Source SHA-256 mismatch");
  await expect(drawer.getByRole("link", { name: "打开原文件" })).toHaveCount(0);
  await drawer.getByRole("button", { name: "获取原文链接" }).first().click();
  await expect(drawer.getByRole("link", { name: "打开原文件" })).toBeVisible();
  expect(calls).toBe(2);
});

test("ordinal zero cursor loads the next passage without repeating the first", async ({ page }) => {
  const second = {
    ...passage,
    passage_id: "22345678-1234-4234-8234-123456789012",
    ordinal: 1,
    text: "Second synthetic passage",
  };
  await page.route(`**/api/backend/knowledge/documents/${documentId}/passages*`, (route) => {
    const cursor = new URL(route.request().url()).searchParams.get("cursor");
    return route.fulfill({
      json: {
        passages: cursor === "0" ? [second] : [passage],
        next_cursor: cursor === "0" ? null : 0,
        fixture: true,
      },
    });
  });
  await page.goto(`/knowledge?document=${documentId}`);
  const drawer = page.getByRole("dialog", { name: `${document.title} 文档详情` });
  await expect(drawer.getByText(passage.text, { exact: true })).toBeVisible();
  await drawer.getByRole("button", { name: "加载更多段落" }).click();
  await expect(drawer.getByText(second.text, { exact: true })).toBeVisible();
  await expect(drawer.getByText(passage.text, { exact: true })).toHaveCount(1);
  await expect(drawer.getByRole("button", { name: "加载更多段落" })).toHaveCount(0);
});

test("OCR job states refresh to actual page regions without a fabricated passage", async ({
  page,
}) => {
  let status = "pending_parse";
  const scanPassage = {
    ...passage,
    page_number: 2,
    text: "Synthetic OCR fixture +123.45 kN",
    native_locator: {
      kind: "docling_pdf_item",
      requires_numeric_review: true,
      regions: [
        {
          page_number: 2,
          page_width: 650,
          page_height: 850,
          bbox: [40, 100, 260, 130],
          coordinate_space: "pdf_points_top_left",
        },
      ],
    },
  };
  await page.route("**/api/knowledge-documents*", (route) =>
    route.fulfill({
      json: {
        ok: true,
        data: {
          documents: [
            {
              ...document,
              ingestionStatus: status,
              vectorized: status === "indexed",
              pageCount: status === "pending_parse" || status === "parsing" ? null : 2,
              requiresNumericReview: status === "pending" || status === "indexed",
            },
          ],
        },
        meta: { fixture: true },
        error: null,
      },
    }),
  );
  await page.route(`**/api/backend/knowledge/documents/${documentId}/passages*`, (route) =>
    route.fulfill({
      json: {
        passages: ["pending", "indexed"].includes(status) ? [scanPassage] : [],
        next_cursor: null,
        fixture: true,
      },
    }),
  );
  await page.goto(`/knowledge?document=${documentId}`);
  const drawer = page.getByRole("dialog", { name: `${document.title} 文档详情` });
  await expect(drawer.getByText("等待 PDF 解析", { exact: true })).toBeVisible();
  await expect(
    drawer.getByText("文档尚在后台解析，暂时没有可引用的段落。", { exact: true }),
  ).toBeVisible();
  await expect(drawer.getByText(scanPassage.text, { exact: true })).toHaveCount(0);
  status = "parsing";
  await expect(drawer.getByText("正在解析 PDF", { exact: true })).toBeVisible({ timeout: 10000 });
  status = "pending";
  await expect(drawer.getByText(scanPassage.text, { exact: true })).toBeVisible({ timeout: 10000 });
  await expect(drawer.getByRole("img", { name: "页面区域示意" })).toBeVisible();
  await expect(drawer.getByText(/数字、正负号、小数点和单位/)).toBeVisible();
  status = "indexed";
  await expect(drawer.getByText("已索引", { exact: true })).toBeVisible({ timeout: 10000 });
  await page.screenshot({
    path: ".artifacts/document-parser-20261007/ocr-source-browser-fixture.png",
    fullPage: true,
  });
});

test("failed PDF parsing has no synthetic text or indexed status", async ({ page }) => {
  await page.route("**/api/knowledge-documents*", (route) =>
    route.fulfill({
      json: {
        ok: true,
        data: { documents: [{ ...document, ingestionStatus: "parse_failed", vectorized: false }] },
        error: null,
      },
    }),
  );
  await page.route(`**/api/backend/knowledge/documents/${documentId}/passages*`, (route) =>
    route.fulfill({
      json: { passages: [], next_cursor: null, fixture: true },
    }),
  );
  await page.goto(`/knowledge?document=${documentId}`);
  const drawer = page.getByRole("dialog", { name: `${document.title} 文档详情` });
  await expect(drawer.getByText("PDF 解析失败", { exact: true })).toBeVisible();
  await expect(drawer.getByRole("alert")).toContainText("未生成可引用正文");
  await expect(drawer.getByText("已索引", { exact: true })).toHaveCount(0);
  await expect(drawer.getByText(passage.text, { exact: true })).toHaveCount(0);
});

test("unknown knowledge registration freezes the file and replays one uploaded object", async ({
  page,
}) => {
  const content = Buffer.from("%PDF-declared-upload-protocol-fixture");
  const calls: { body: Record<string, unknown>; key: string | undefined }[] = [];
  let putCount = 0;
  let presignCount = 0;
  await page.route("**/api/backend/knowledge/documents/uploads/presign", (route) => {
    presignCount++;
    const body = route.request().postDataJSON();
    expect(body.artifact_sha256).toBe(createHash("sha256").update(content).digest("hex"));
    return route.fulfill({
      json: {
        artifact_uri: `minio://fixture/documents/${body.document_id}/source.pdf`,
        upload_url: new URL("/__e2e/knowledge-upload", route.request().url()).href,
        required_headers: { "Content-Type": "application/pdf" },
        expires_at: new Date(Date.now() + 300_000).toISOString(),
      },
    });
  });
  await page.route("**/__e2e/knowledge-upload", (route) => {
    putCount++;
    expect(route.request().postDataBuffer()).toEqual(content);
    return route.fulfill({ status: 200, body: "" });
  });
  await page.route("**/api/backend/knowledge/documents", (route) => {
    calls.push({
      body: route.request().postDataJSON(),
      key: route.request().headers()["idempotency-key"],
    });
    if (calls.length < 3)
      return route.fulfill({
        status: calls.length === 1 ? 503 : 403,
        json: {
          error: { code: "DECLARED_UI_CHALLENGE", message: "Declared ambiguous/denied response" },
        },
      });
    return route.fulfill({
      status: 202,
      json: { document_id: calls[0].body.document_id, ingestion_status: "pending_parse" },
    });
  });
  await page.goto("/knowledge");
  const checkbox = page.getByRole("checkbox", { name: "PDF 扫描件解析" });
  await expect(checkbox).toBeEnabled();
  await checkbox.check();
  await page
    .locator('input[type="file"]')
    .setInputFiles({ name: "synthetic-scan.pdf", mimeType: "application/pdf", buffer: content });
  const reconcile = page.getByRole("button", { name: "核验同一提交" });
  await expect(reconcile).toBeVisible();
  await expect(page.getByRole("button", { name: "上传知识制品" })).toBeDisabled();
  await expect(checkbox).toBeDisabled();
  await reconcile.click();
  await expect(page.getByRole("alert").filter({ hasText: "知识提交响应未确认" })).toContainText(
    "Declared ambiguous/denied response",
  );
  await expect(reconcile).toBeEnabled();
  await expect(page.getByRole("button", { name: "上传知识制品" })).toBeDisabled();
  await reconcile.click();
  await expect(reconcile).toHaveCount(0);
  await expect(page.getByRole("button", { name: "上传知识制品" })).toBeEnabled();
  expect(calls).toHaveLength(3);
  expect(calls[1]).toEqual(calls[0]);
  expect(calls[2]).toEqual(calls[0]);
  expect(calls[0].body.parser).toBe("docling");
  expect(putCount).toBe(1);
  expect(presignCount).toBe(1);
});

test("failed parser configuration can be explicitly reloaded without enabling an unknown capability", async ({
  page,
}) => {
  let calls = 0;
  await page.route("**/api/backend/knowledge/parser-capabilities", (route) => {
    calls++;
    return calls <= 2
      ? route.fulfill({
          status: 503,
          json: {
            error: {
              code: "READ_AUDIT_UNAVAILABLE",
              message: "Declared configuration read unavailable",
            },
          },
        })
      : route.fulfill({
          json: { docling_pdf_configured: true, max_artifact_bytes: 52428800, fixture: true },
        });
  });
  await page.goto("/knowledge");
  const checkbox = page.getByRole("checkbox", { name: "PDF 扫描件解析" });
  await expect(checkbox).toBeDisabled();
  const retry = page.getByRole("button", { name: "重试解析配置" });
  await expect(retry).toBeVisible({ timeout: 10_000 });
  await retry.click();
  await expect(checkbox).toBeEnabled();
  await expect(retry).toHaveCount(0);
  expect(calls).toBe(3);
});
