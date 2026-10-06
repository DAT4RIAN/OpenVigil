import { expect, test } from "@playwright/test";

// Explicit transport fixtures verify the inspector only. SQL, original bytes
// and concurrent withdrawals are challenged separately in backend tests.
const claimId = "SYNTHETIC-APPROVED-GRAPH-CLAIM";
const node = {
  uid: `EngineeringClaim:${claimId}`,
  entityId: claimId,
  type: "EngineeringClaim",
  properties: {
    revision: 2,
    reviewStatus: "approved",
    recordSemantics: "reviewed_engineering_statement",
    conclusion: "Synthetic reviewed graph conclusion",
    authorizesWork: false,
    fieldQualification: "unverified",
  },
};

test("graph controls protect early input before hydration", async ({ browser, baseURL }) => {
  const context = await browser.newContext({
    baseURL,
    javaScriptEnabled: false,
    extraHTTPHeaders: {
      "oai-authenticated-user-id": "user-manager",
      "oai-authenticated-user-email": "manager@example.com",
      "x-e2e-runtime": "production",
    },
  });
  try {
    const page = await context.newPage();
    await page.goto("/knowledge-graph");
    await expect(page.getByRole("textbox", { name: "图谱实体 ID" })).toBeDisabled();
    await expect(page.getByRole("combobox", { name: "关系深度" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "查询", exact: true })).toBeDisabled();
    await expect(page.getByRole("textbox", { name: "知识图谱混合检索问题" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "检索并扩图", exact: true })).toBeDisabled();
  } finally {
    await context.close();
  }
});

test("graph inspector distinguishes reviewed statements and clears revoked cached results", async ({
  page,
  context,
}) => {
  await context.setExtraHTTPHeaders({
    "oai-authenticated-user-id": "user-manager",
    "oai-authenticated-user-email": "manager@example.com",
    "x-e2e-runtime": "production",
  });
  let withdrawn = false;
  let releaseWithdrawal: () => void = () => undefined;
  const withdrawalBarrier = new Promise<void>((resolve) => {
    releaseWithdrawal = resolve;
  });
  let observeWithdrawal: () => void = () => undefined;
  const withdrawalRequested = new Promise<void>((resolve) => {
    observeWithdrawal = resolve;
  });
  await page.route("**/api/knowledge-graph?*", async (route) => {
    if (withdrawn) {
      observeWithdrawal();
      await withdrawalBarrier;
      return route.fulfill({
        status: 404,
        json: { error: { code: "NOT_FOUND", message: "Synthetic claim has been withdrawn" } },
      });
    }
    return route.fulfill({
      json: {
        data: {
          summary: {
            backend: "explicit-browser-fixture",
            projectionId: "synthetic",
            sourceRevision: "synthetic-revision",
            generatedAt: null,
            nodeCount: 1,
            relationshipCount: 0,
            orphanNodeCount: 1,
            nodeTypeCounts: { EngineeringClaim: 1 },
          },
          graph: { rootUid: node.uid, nodes: [node], relationships: [] },
        },
        meta: {
          authoritativeSource: "explicit-browser-fixture",
          projectionBackend: "explicit-browser-fixture",
          consistency: "transport-fixture-only",
          entityId: claimId,
          depth: 4,
        },
      },
    });
  });
  await page.goto("/knowledge-graph");
  await expect(page.getByRole("textbox", { name: "图谱实体 ID" })).toBeEnabled();
  await page.getByRole("textbox", { name: "图谱实体 ID" }).fill(claimId);
  await page.getByRole("button", { name: "查询", exact: true }).click();
  await expect(page.getByRole("note")).toContainText("独立审核的工程结论 · 修订 2");
  await expect(page.getByRole("note")).toContainText("不授权作业，现场资格未验证");
  await expect(page.getByText(node.properties.conclusion, { exact: true })).toBeVisible();
  withdrawn = true;
  await page.getByRole("button", { name: "刷新", exact: true }).click();
  await withdrawalRequested;
  try {
    await expect(page.getByRole("note")).toHaveCount(0);
    await expect(page.getByText(node.properties.conclusion, { exact: true })).toHaveCount(0);
  } finally {
    releaseWithdrawal();
  }
  await expect(page.getByRole("alert")).toContainText("Synthetic claim has been withdrawn");
  await expect(page.getByRole("note")).toHaveCount(0);
  await expect(page.getByText(node.properties.conclusion, { exact: true })).toHaveCount(0);
  await expect(page.getByText(node.uid, { exact: true })).toHaveCount(0);
});
