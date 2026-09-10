import { expect, test } from "@playwright/test";

const routes = [
  "/",
  "/wind-farms",
  "/turbines/WT-023",
  "/scada",
  "/health",
  "/alarms",
  "/diagnosis",
  "/predictive-maintenance",
  "/agents",
  "/missions",
  "/missions/MISSION-2026-0823",
  "/decisions",
  "/work-orders",
  "/maintenance",
  "/resources",
  "/knowledge",
  "/digital-twin",
  "/knowledge-graph",
  "/data",
  "/reports",
  "/models",
  "/settings",
] as const;

const forbiddenConclusion =
  /预计\s*RUL|预计剩余寿命|30\s*[天日]\s*失效概率|失效概率\s*(?:为\s*)?\d|RUL\s*(?:为\s*)?\d|剩余寿命\s*(?:为\s*)?\d|Probability\s*×\s*Consequence/i;

test("all 22 demo routes keep unvalidated lifetime conclusions out of operational content", async ({
  browser,
}, testInfo) => {
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:4179",
    viewport: { width: 1440, height: 900 },
    extraHTTPHeaders: { "x-e2e-runtime": "demo" },
  });
  const page = await context.newPage();

  for (const route of routes) {
    await page.goto(route, { waitUntil: "domcontentloaded" });
    await expect(page.locator("main.app-main")).toBeVisible();
    const content = await page.locator("body").innerText();
    expect(content, route).not.toMatch(forbiddenConclusion);

    if (
      ["/health", "/predictive-maintenance", "/digital-twin", "/turbines/WT-023"].includes(route)
    ) {
      await page.screenshot({
        path: testInfo.outputPath(`${route.replaceAll("/", "-").replace(/^-/, "")}.png`),
        fullPage: true,
      });
    }
  }

  await context.close();
});
