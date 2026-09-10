import { expect, test, type Browser, type Page } from "@playwright/test";

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

async function demoPage(browser: Browser, width: number, height: number) {
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:4179",
    viewport: { width, height },
    extraHTTPHeaders: { "x-e2e-runtime": "demo" },
  });
  await context.addInitScript(() => {
    if (sessionStorage.getItem("openvigil-sidebar-test-initialized")) return;
    localStorage.removeItem("openvigil-sidebar-collapsed");
    localStorage.removeItem("windops-sidebar-collapsed");
    sessionStorage.setItem("openvigil-sidebar-test-initialized", "true");
  });
  return { context, page: await context.newPage() };
}

async function touchTargetViolations(page: Page) {
  return page
    .locator(
      [
        "button",
        "[role='button']",
        "summary",
        "input:not([type='checkbox']):not([type='radio']):not([type='file'])",
        "select",
        "textarea",
        "a.nav-item",
        "a.farm-switcher",
        "tbody tr[tabindex]",
      ].join(","),
    )
    .evaluateAll((elements) =>
      elements
        .filter((element) => {
          const style = getComputedStyle(element);
          const rect = element.getBoundingClientRect();
          return (
            style.display !== "none" &&
            style.visibility !== "hidden" &&
            rect.width > 0 &&
            rect.height > 0 &&
            rect.right > 0 &&
            rect.left < window.innerWidth
          );
        })
        .map((element) => {
          const rect = element.getBoundingClientRect();
          return {
            label:
              element.getAttribute("aria-label") ??
              element.textContent?.replace(/\s+/g, " ").trim().slice(0, 48) ??
              element.tagName,
            width: Math.round(rect.width * 10) / 10,
            height: Math.round(rect.height * 10) / 10,
          };
        })
        .filter(({ width, height }) => width < 44 || height < 44),
    );
}

test("900px uses an inert, modal navigation drawer with focus return", async ({
  browser,
}, testInfo) => {
  const { context, page } = await demoPage(browser, 900, 800);
  await page.goto("/", { waitUntil: "domcontentloaded" });
  const menuButton = page.getByRole("button", { name: "打开导航" });
  const sidebar = page.locator("#openvigil-primary-sidebar");

  await expect(menuButton).toBeVisible();
  await expect(menuButton).toHaveAttribute("aria-expanded", "false");
  await expect(sidebar).toHaveAttribute("aria-hidden", "true");
  expect(
    await page.locator(".app-column").evaluate((element) => element.getBoundingClientRect().width),
  ).toBeGreaterThanOrEqual(899);

  await menuButton.click();
  const drawer = page.getByRole("dialog", { name: "主导航抽屉" });
  await expect(drawer).toBeVisible();
  await expect(menuButton).toHaveAttribute("aria-expanded", "true");
  await expect(drawer.locator("a, button").first()).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  expect(
    await page.evaluate(
      () => document.activeElement?.closest("#openvigil-primary-sidebar") !== null,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("tablet-900-drawer-open.png"),
    fullPage: true,
  });

  await page.keyboard.press("Escape");
  await expect(menuButton).toHaveAttribute("aria-expanded", "false");
  await expect(menuButton).toBeFocused();
  await expect(sidebar).toHaveAttribute("aria-hidden", "true");
  await context.close();

  const zoom = await demoPage(browser, 720, 450);
  await zoom.page.goto("/", { waitUntil: "domcontentloaded" });
  const zoomMenu = zoom.page.getByRole("button", { name: "打开导航" });
  await zoomMenu.click();
  await expect(zoom.page.getByRole("dialog", { name: "主导航抽屉" })).toBeVisible();
  await zoom.page.keyboard.press("Escape");
  await expect(zoomMenu).toBeFocused();
  await zoom.context.close();
});

test("laptop sidebar defaults collapsed and persists the operator choice", async ({
  browser,
}, testInfo) => {
  for (const width of [1024, 1280]) {
    const { context, page } = await demoPage(browser, width, 800);
    await page.goto("/", { waitUntil: "domcontentloaded" });
    const shell = page.locator(".app-shell");
    const sidebar = page.locator("#openvigil-primary-sidebar");

    await expect(shell).toHaveClass(/app-shell--collapsed/);
    await expect(page.getByRole("button", { name: "打开导航" })).toBeHidden();
    expect(
      await page.locator(".app-main").evaluate((element) => element.getBoundingClientRect().width),
    ).toBeGreaterThanOrEqual(760);

    await page.getByRole("button", { name: "展开侧栏" }).click();
    await expect(shell).not.toHaveClass(/app-shell--collapsed/);
    expect(await page.evaluate(() => localStorage.getItem("openvigil-sidebar-collapsed"))).toBe(
      "false",
    );
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(shell).not.toHaveClass(/app-shell--collapsed/);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: testInfo.outputPath(`laptop-${width}-expanded.png`),
      fullPage: false,
    });

    await page.getByRole("button", { name: "收起侧栏" }).click();
    expect(await page.evaluate(() => localStorage.getItem("openvigil-sidebar-collapsed"))).toBe(
      "true",
    );
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(shell).toHaveClass(/app-shell--collapsed/);
    await expect
      .poll(() => sidebar.evaluate((element) => element.getBoundingClientRect().width))
      .toBeLessThan(80);
    await context.close();
  }
});

test("mobile controls and clickable rows meet the 44px target without page overflow", async ({
  browser,
}) => {
  const { context, page } = await demoPage(browser, 390, 844);
  const violations: Array<{
    route: string;
    targets: Awaited<ReturnType<typeof touchTargetViolations>>;
  }> = [];

  for (const route of routes) {
    await page.goto(route, { waitUntil: "domcontentloaded" });
    await expect(page.locator("main.app-main")).toBeVisible();
    const targets = await touchTargetViolations(page);
    if (targets.length) violations.push({ route, targets });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth),
      `${route} document overflow`,
    ).toBeLessThanOrEqual(1);
  }
  expect(violations).toEqual([]);

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: "打开导航" }).click();
  await expect(page.getByRole("dialog", { name: "主导航抽屉" })).toBeVisible();
  expect(await touchTargetViolations(page), "390px open navigation targets").toEqual([]);
  await page.keyboard.press("Escape");
  await context.close();

  for (const width of [320, 360, 430]) {
    const sample = await demoPage(browser, width, 844);
    await sample.page.goto("/", { waitUntil: "domcontentloaded" });
    expect(await touchTargetViolations(sample.page), `${width}px touch targets`).toEqual([]);
    expect(
      await sample.page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth),
      `${width}px document overflow`,
    ).toBeLessThanOrEqual(1);
    await sample.context.close();
  }
});
