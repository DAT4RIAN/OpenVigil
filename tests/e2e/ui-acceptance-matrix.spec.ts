import { expect, test, type Browser, type Page } from "@playwright/test";
import axeCore from "axe-core";
import { routeAcceptanceMatrix, viewportAcceptanceMatrix } from "./ui-acceptance-matrix";

const baseURL = "http://127.0.0.1:4179";

async function demoPage(
  browser: Browser,
  viewport: { readonly width: number; readonly height: number },
  reducedMotion: "reduce" | "no-preference" = "no-preference",
) {
  const context = await browser.newContext({
    baseURL,
    viewport,
    reducedMotion,
    extraHTTPHeaders: { "x-e2e-runtime": "demo" },
  });
  return { context, page: await context.newPage() };
}

async function seriousAxeViolations(page: Page) {
  await page.addScriptTag({ content: axeCore.source });
  return page.evaluate(async () => {
    const axe = (
      globalThis as unknown as {
        axe: {
          run: (
            root: Document,
            options: Record<string, unknown>,
          ) => Promise<{
            violations: Array<{
              id: string;
              impact: string | null;
              help: string;
              nodes: Array<{ target: string[]; failureSummary?: string }>;
            }>;
          }>;
        };
      }
    ).axe;
    const results = await axe.run(document, {
      runOnly: {
        type: "tag",
        values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"],
      },
    });
    return results.violations
      .filter((violation) => violation.impact === "critical" || violation.impact === "serious")
      .map((violation) => ({
        id: violation.id,
        impact: violation.impact,
        help: violation.help,
        nodes: violation.nodes.slice(0, 8).map((node) => ({
          target: node.target,
          failureSummary: node.failureSummary,
        })),
      }));
  });
}

test("all 22 routes pass the viewport, heading, navigation, and overflow matrix", async ({
  browser,
}) => {
  test.setTimeout(180_000);
  for (const viewport of viewportAcceptanceMatrix) {
    const { context, page } = await demoPage(browser, viewport);
    const pageErrors: string[] = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));

    for (const route of routeAcceptanceMatrix) {
      pageErrors.length = 0;
      const response = await page.goto(route.path, { waitUntil: "domcontentloaded" });
      expect(response?.status(), `${viewport.name} ${route.path} document response`).toBeLessThan(
        400,
      );
      await expect(
        page.locator("main.app-main"),
        `${viewport.name} ${route.path} main`,
      ).toBeVisible();
      await expect(page.locator("h1"), `${viewport.name} ${route.path} unique H1`).toHaveCount(1);
      await expect(page.locator("h1"), `${viewport.name} ${route.path} visible H1`).toBeVisible();
      const current = page.locator('.sidebar__nav a[aria-current="page"]');
      await expect(current, `${viewport.name} ${route.path} one current nav item`).toHaveCount(1);
      await expect(current, `${viewport.name} ${route.path} navigation owner`).toHaveAttribute(
        "href",
        route.owner,
      );
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth),
        `${viewport.name} ${route.path} document overflow`,
      ).toBeLessThanOrEqual(1);
      await expect(
        page.locator(".route-state"),
        `${viewport.name} ${route.path} fatal route state`,
      ).toHaveCount(0);
      expect(pageErrors, `${viewport.name} ${route.path} uncaught page errors`).toEqual([]);
    }
    await context.close();
  }
});

test("dashboard full-page visual baselines cover desktop, compact desktop, and mobile", async ({
  browser,
}) => {
  for (const viewport of viewportAcceptanceMatrix.filter((item) => item.name !== "tablet-900")) {
    const { context, page } = await demoPage(browser, viewport);
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.locator("h1")).toHaveText("运营指挥中心");
    await expect(page.locator(".brand-lockup strong")).toHaveText("OpenVigil");
    await expect(page).toHaveScreenshot(`dashboard-${viewport.name}.png`, {
      animations: "disabled",
      fullPage: true,
      maxDiffPixelRatio: 0.01,
    });
    await context.close();
  }
});

test("critical routes have no serious WCAG violations on desktop or mobile", async ({
  browser,
}) => {
  test.setTimeout(120_000);
  const criticalRoutes = routeAcceptanceMatrix.filter((route) => route.risk === "critical");
  for (const viewport of [viewportAcceptanceMatrix[0], viewportAcceptanceMatrix[3]]) {
    const { context, page } = await demoPage(browser, viewport);
    for (const route of criticalRoutes) {
      await page.goto(route.path, { waitUntil: "domcontentloaded" });
      await expect(page.locator("h1")).toBeVisible();
      expect(await seriousAxeViolations(page), `${viewport.name} ${route.path}`).toEqual([]);
    }
    await context.close();
  }
});

test("Mission ownership, return path, and reduced motion remain keyboard operable", async ({
  browser,
}) => {
  const { context, page } = await demoPage(browser, viewportAcceptanceMatrix[0], "reduce");
  await page.goto("/missions");
  const missionLink = page.locator('a[href="/missions/MISSION-2026-0823"]').first();
  await missionLink.focus();
  await expect(missionLink).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/missions\/MISSION-2026-0823$/);
  await expect(page.locator('.sidebar__nav a[aria-current="page"]')).toHaveAttribute(
    "href",
    "/missions",
  );
  const returnLink = page.getByRole("link", { name: "返回Mission 中心" });
  await expect(returnLink).toHaveAttribute("href", "/missions");
  await returnLink.focus();
  await expect(returnLink).toBeFocused();
  await returnLink.press("Enter");
  await expect(page).toHaveURL(/\/missions$/);

  const motionViolations = await page.locator("body *").evaluateAll((nodes) =>
    nodes
      .filter((node) => {
        const element = node as HTMLElement;
        const style = getComputedStyle(element);
        if (!element.getClientRects().length || style.visibility === "hidden") return false;
        const durations = (value: string) =>
          value
            .split(",")
            .map((item) =>
              item.trim().endsWith("ms")
                ? Number.parseFloat(item)
                : Number.parseFloat(item) * 1_000,
            );
        return (
          durations(style.animationDuration).some((duration) => duration > 10) ||
          durations(style.transitionDuration).some((duration) => duration > 10)
        );
      })
      .slice(0, 10)
      .map((node) => ({ tag: node.tagName, className: (node as HTMLElement).className })),
  );
  expect(motionViolations).toEqual([]);
  await context.close();
});
