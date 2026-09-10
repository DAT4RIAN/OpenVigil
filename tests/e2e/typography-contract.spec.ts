import { expect, test, type Page } from "@playwright/test";

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

async function textScaleViolations(page: Page) {
  return page.locator("body").evaluate(() => {
    const isVisible = (element: Element) => {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return (
        style.display !== "none" &&
        style.visibility !== "hidden" &&
        Number(style.opacity) !== 0 &&
        rect.width > 0 &&
        rect.height > 0
      );
    };
    const hasDirectText = (element: Element) =>
      [...element.childNodes].some(
        (node) => node.nodeType === Node.TEXT_NODE && Boolean(node.textContent?.trim()),
      );
    const describe = (element: Element) => {
      const html = element as HTMLElement;
      const classes = typeof html.className === "string" ? html.className.split(" ")[0] : "";
      const text = element.textContent?.replace(/\s+/g, " ").trim().slice(0, 36) ?? "";
      return `${element.tagName.toLowerCase()}${element.id ? `#${element.id}` : ""}${classes ? `.${classes}` : ""}[${text}]`;
    };
    const visibleText = [...document.body.querySelectorAll("*")].filter(
      (element) => isVisible(element) && hasDirectText(element),
    );
    const belowMetadata = visibleText
      .filter((element) => Number.parseFloat(getComputedStyle(element).fontSize) < 11)
      .map((element) => `${describe(element)}=${getComputedStyle(element).fontSize}`);
    const actionOrKey = visibleText.filter((element) =>
      element.matches("button, a, strong, th, [role='button'], .status-badge"),
    );
    const belowAction = actionOrKey
      .filter((element) => Number.parseFloat(getComputedStyle(element).fontSize) < 12)
      .map((element) => `${describe(element)}=${getComputedStyle(element).fontSize}`);
    const belowTable = [...document.body.querySelectorAll("th, td")]
      .filter(isVisible)
      .filter((element) => Number.parseFloat(getComputedStyle(element).fontSize) < 13)
      .map((element) => `${describe(element)}=${getComputedStyle(element).fontSize}`);
    return { belowMetadata, belowAction, belowTable };
  });
}

test("all 22 workspaces honor the semantic typography floor", async ({ browser }) => {
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:4179",
    viewport: { width: 1440, height: 900 },
    extraHTTPHeaders: { "x-e2e-runtime": "demo" },
  });
  const page = await context.newPage();
  const violations: Array<{
    route: string;
    findings: Awaited<ReturnType<typeof textScaleViolations>>;
  }> = [];

  for (const route of routes) {
    await page.goto(route, { waitUntil: "domcontentloaded" });
    await expect(page.locator("main.app-main")).toBeVisible();
    const findings = await textScaleViolations(page);
    if (
      findings.belowMetadata.length ||
      findings.belowAction.length ||
      findings.belowTable.length
    ) {
      violations.push({ route, findings });
    }
  }

  expect(violations).toEqual([]);
  await context.close();
});

test("dashboard typography remains legible across target viewports", async ({
  browser,
}, testInfo) => {
  for (const viewport of [
    { width: 1440, height: 900, name: "desktop" },
    { width: 1280, height: 800, name: "laptop" },
    { width: 390, height: 844, name: "mobile" },
  ]) {
    const context = await browser.newContext({
      baseURL: "http://127.0.0.1:4179",
      viewport,
      extraHTTPHeaders: { "x-e2e-runtime": "demo" },
    });
    const page = await context.newPage();
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.locator("main.app-main")).toBeVisible();
    expect(await textScaleViolations(page), viewport.name).toEqual({
      belowMetadata: [],
      belowAction: [],
      belowTable: [],
    });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth),
      `${viewport.name} document overflow`,
    ).toBeLessThanOrEqual(1);
    await page.screenshot({
      path: testInfo.outputPath(`dashboard-typography-${viewport.width}x${viewport.height}.png`),
      fullPage: true,
    });
    await context.close();
  }
});

test("200 percent zoom equivalent keeps key workspaces operable and unclipped", async ({
  browser,
}, testInfo) => {
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:4179",
    viewport: { width: 720, height: 450 },
    extraHTTPHeaders: { "x-e2e-runtime": "demo" },
  });
  const page = await context.newPage();

  for (const route of [
    "/",
    "/missions/MISSION-2026-0823",
    "/decisions",
    "/work-orders",
    "/models",
    "/data",
  ] as const) {
    await page.goto(route, { waitUntil: "domcontentloaded" });
    await expect(page.locator("main.app-main")).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth),
      `${route} document overflow at 200% zoom equivalent`,
    ).toBeLessThanOrEqual(1);
    const clippedKeyText = await page
      .locator("h1, h2, h3, button, .status-badge, .page-header__copy > p")
      .evaluateAll((elements) =>
        elements
          .filter((element) => {
            const html = element as HTMLElement;
            const style = getComputedStyle(html);
            const rect = html.getBoundingClientRect();
            return (
              rect.width > 0 &&
              rect.height > 0 &&
              ["hidden", "clip"].includes(style.overflowX) &&
              html.scrollWidth > html.clientWidth + 1
            );
          })
          .map((element) => element.textContent?.replace(/\s+/g, " ").trim().slice(0, 60)),
      );
    expect(clippedKeyText, `${route} clipped key text at 200% zoom equivalent`).toEqual([]);

    if (route === "/" || route === "/missions/MISSION-2026-0823" || route === "/models") {
      await page.screenshot({
        path: testInfo.outputPath(
          `zoom-200-${route === "/" ? "dashboard" : route.split("/").at(-1)}.png`,
        ),
        fullPage: true,
      });
    }
  }

  await context.close();
});
