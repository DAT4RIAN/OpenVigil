import { expect, test } from "@playwright/test";

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
