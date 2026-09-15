import { expect, test } from "@playwright/test";
import axeCore from "axe-core";

test("theme choice persists and key surfaces remain accessible in both themes", async ({
  browser,
}) => {
  test.setTimeout(90_000);
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:4179",
    viewport: { width: 1440, height: 900 },
    extraHTTPHeaders: { "x-e2e-runtime": "demo" },
  });
  const page = await context.newPage();
  try {
    await page.goto("/");
    await page.getByRole("button", { name: "当前浅色，点击切换主题" }).click();
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

    for (const theme of ["dark", "light"] as const) {
      if (theme === "light") {
        await page.getByRole("button", { name: "当前深色，点击切换主题" }).click();
        await page.getByRole("button", { name: "当前跟随系统，点击切换主题" }).click();
      }
      for (const route of ["/", "/alarms", "/missions/MISSION-2026-0823"]) {
        await page.goto(route);
        await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
        await expect(page.locator("main h1")).toBeVisible();
        await page.addScriptTag({ content: axeCore.source });
        const violations = await page.evaluate(async () => {
          const axe = (window as unknown as { axe: typeof axeCore }).axe;
          const { violations } = await axe.run(document, {
            runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] },
          });
          return violations
            .filter((item) => item.impact === "serious" || item.impact === "critical")
            .map((item) => ({
              id: item.id,
              nodes: item.nodes.map((node) => ({
                target: node.target,
                summary: node.failureSummary,
              })),
            }));
        });
        expect(violations, `${theme} ${route}`).toEqual([]);
      }
    }
  } finally {
    await context.close();
  }
});

test("phone first screen shows the incident action and metrics without clipping", async ({
  browser,
}) => {
  for (const width of [320, 375, 390, 414, 768]) {
    const context = await browser.newContext({
      baseURL: "http://127.0.0.1:4179",
      viewport: { width, height: 844 },
      reducedMotion: "reduce",
      extraHTTPHeaders: { "x-e2e-runtime": "demo" },
    });
    try {
      const page = await context.newPage();
      await page.goto("/");
      const action = page.locator(".incident-link");
      await expect(action).toBeVisible();
      const box = await action.boundingBox();
      expect(box!.y + box!.height, `${width}px incident action`).toBeLessThan(844);
      const firstMetric = await page.locator(".metrics-grid > :first-child").boundingBox();
      expect(firstMetric!.y + firstMetric!.height, `${width}px first metric`).toBeLessThan(844);
      const clipped = await page
        .locator(".incident-signals dd, .metric-card__value, .metric-card__top")
        .evaluateAll((elements) =>
          elements
            .filter((element) => element.scrollWidth > element.clientWidth + 1)
            .map((element) => element.textContent),
        );
      expect(clipped, `${width}px clipped incident or KPI text`).toEqual([]);
      await action.focus();
      await expect(action).toBeFocused();
    } finally {
      await context.close();
    }
  }
});

test("Mission context cards stay inside their column beside the timeline", async ({ browser }) => {
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:4179",
    extraHTTPHeaders: { "x-e2e-runtime": "demo" },
  });
  try {
    const page = await context.newPage();
    for (const width of [1440, 1280, 1024, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/missions/MISSION-2026-0823");
      await expect(page.locator(".mission-context-column")).toBeVisible();
      const overflowing = await page.locator(".mission-context-column").evaluate((column) => {
        const bounds = column.getBoundingClientRect();
        return [...column.querySelectorAll("*")]
          .filter((element) => {
            const rect = element.getBoundingClientRect();
            return rect.width > 0 && (rect.right > bounds.right + 1 || rect.left < bounds.left - 1);
          })
          .map((element) => element.className);
      });
      expect(overflowing, `${width}px overlapping Mission context`).toEqual([]);
    }
  } finally {
    await context.close();
  }
});
