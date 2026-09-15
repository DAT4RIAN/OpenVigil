import { expect, test } from "@playwright/test";
import axeCore from "axe-core";

test.use({ extraHTTPHeaders: { "x-e2e-runtime": "demo" } });

test("page entrance reaches its original layout and cancels when reduced motion changes", async ({
  page,
}) => {
  // Pause real browser animations so both frames can be checked without timing races.
  await page.addInitScript(() => {
    const animate = Object.getOwnPropertyDescriptor(Element.prototype, "animate")!
      .value as Element["animate"];
    Element.prototype.animate = function (...args) {
      const animation = animate.apply(this, args);
      if (this.matches(".app-main, .page-header")) animation.pause();
      return animation;
    };
  });
  await page.goto("/");
  const main = page.locator(".app-main");
  const heading = page.locator(".page-header");
  await expect.poll(() => heading.evaluate((element) => element.getAnimations().length)).toBe(1);
  const start = await main.evaluate((element) => {
    element
      .getAnimations({ subtree: true })
      .filter((animation) => animation.playState === "paused")
      .forEach((animation) => {
        animation.currentTime = 0;
      });
    return {
      opacity: Number(getComputedStyle(element).opacity),
      heading: element.querySelector(".page-header")!.getBoundingClientRect().top,
    };
  });
  expect(start.opacity).toBe(1);
  await page.addScriptTag({ content: axeCore.source });
  const contrastViolations = await page.evaluate(async () => {
    const axe = (window as unknown as { axe: typeof axeCore }).axe;
    return (await axe.run(document, { runOnly: ["color-contrast"] })).violations;
  });
  expect(contrastViolations).toEqual([]);
  await page.screenshot({ path: ".artifacts/motion/page-enter-start.png" });
  await main.evaluate((element) => {
    element
      .getAnimations({ subtree: true })
      .filter((animation) => animation.playState === "paused")
      .forEach((animation) => animation.finish());
  });
  const end = await main.evaluate((element) => ({
    opacity: Number(getComputedStyle(element).opacity),
    heading: element.querySelector(".page-header")!.getBoundingClientRect().top,
  }));
  expect(end.opacity).toBe(1);
  expect(start.heading - end.heading).toBeCloseTo(6, 0);
  await page.screenshot({ path: ".artifacts/motion/page-enter-end.png" });

  await page.goto("/missions");
  await expect.poll(() => heading.evaluate((element) => element.getAnimations().length)).toBe(1);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect.poll(() => heading.evaluate((element) => element.getAnimations().length)).toBe(0);
  await expect(main).toHaveCSS("opacity", "1");
  await expect(page.locator(".page-header")).toHaveCSS("transform", "none");
});

test("search and detail layers animate while retaining immediate escape and focus return", async ({
  page,
}) => {
  await page.goto("/");
  const search = page.getByRole("button", { name: "打开全局搜索" });
  await search.click();
  const dialog = page.locator(".command-dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveCSS("animation-name", "command-enter");
  await expect(dialog.locator("input")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(search).toBeFocused();

  await page.goto("/agents");
  await page.locator("button.agent-card").first().click();
  const drawer = page.locator(".detail-drawer");
  await expect(drawer).toBeVisible();
  await expect(drawer).toHaveCSS("animation-name", "drawer-enter");
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
  await expect(page.locator("button.agent-card").first()).toBeFocused();
});

test("reduced motion keeps login, mobile navigation and overlays fully usable", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "欢迎回到 OpenVigil" })).toBeVisible();
  expect(
    await page.evaluate(
      () =>
        document.getAnimations().filter((animation) => animation.playState === "running").length,
    ),
  ).toBe(0);
  await page.getByRole("link", { name: "进入演示工作台" }).click();
  await expect(page.locator(".app-main")).toHaveCSS("opacity", "1");
  expect(
    await page.locator(".app-main").evaluate((element) => element.getAnimations().length),
  ).toBe(0);
  await page.getByRole("button", { name: "打开导航" }).click();
  await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "打开导航" })).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("login entrance settles into a stable actionable page on desktop and mobile", async ({
  page,
}) => {
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/login");
    const action = page.getByRole("link", { name: "进入演示工作台" });
    await expect(action).toHaveCSS("animation-duration", "0.36s");
    await expect
      .poll(() =>
        page.evaluate(
          () =>
            document.getAnimations().filter((animation) => animation.playState === "running")
              .length,
        ),
      )
      .toBe(0);
    await expect(action).toHaveCSS("opacity", "1");
    await action.focus();
    await expect(action).toBeFocused();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({ path: `.artifacts/motion/login-settled-${width}.png`, fullPage: true });
  }
});
