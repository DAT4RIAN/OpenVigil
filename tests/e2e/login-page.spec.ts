import axeCore from "axe-core";
import { expect, test } from "@playwright/test";

test("public production login preserves the destination through the hosted identity entry", async ({
  page,
}) => {
  await page.goto("/missions?status=open");
  await expect(page).toHaveURL(/\/login\?return_to=/);
  await expect(page.getByRole("heading", { name: "欢迎回到 OpenVigil" })).toBeVisible();
  await expect(page.locator(".app-shell")).toHaveCount(0);
  const signIn = page.getByRole("link", { name: "使用 ChatGPT 登录" });
  await expect(signIn).toHaveAttribute(
    "href",
    "/signin-with-chatgpt?return_to=%2Fmissions%3Fstatus%3Dopen",
  );
  await signIn.click();
  await expect(page.getByRole("heading", { name: "Sites dispatcher sign-in" })).toBeVisible();
});

test("public login does not accept forged capability sessions", async ({ page }) => {
  await page.setExtraHTTPHeaders({
    "oai-authenticated-user-id": "user-manager",
    "x-windops-trusted-session": "forged-manager-session",
    "x-windops-capabilities": "platform.manage",
  });
  await page.goto("/login?return_to=https%3A%2F%2Fevil.example");
  await expect(page.getByRole("link", { name: "使用 ChatGPT 登录" })).toHaveAttribute(
    "href",
    "/signin-with-chatgpt?return_to=%2F",
  );
  await expect(page.locator(".app-shell")).toHaveCount(0);
  await expect(page.locator('input[type="password"]')).toHaveCount(0);
});

test("demo login enters the requested working page without granting production identity", async ({
  page,
}) => {
  await page.setExtraHTTPHeaders({ "x-e2e-runtime": "demo" });
  await page.goto("/login?return_to=%2Fmissions");
  await expect(page.getByText("演示入口不授予生产环境访问权限")).toBeVisible();
  await page.getByRole("link", { name: "进入演示工作台" }).click();
  await expect(page).toHaveURL(/\/missions$/);
  await expect(page.locator(".app-shell")).toBeVisible();
  await page.getByRole("link", { name: "打开登录页面" }).click();
  await expect(page).toHaveURL(/\/login$/);
});

test("offline login gives a recoverable error and keyboard-accessible help", async ({
  page,
  context,
}) => {
  await page.goto("/login");
  const action = page.getByRole("link", { name: "使用 ChatGPT 登录" });
  await action.focus();
  await expect(action).toBeFocused();
  await context.setOffline(true);
  await action.press("Enter");
  await expect(page.getByRole("alert")).toContainText("网络连接已断开");
  await expect(action).toHaveAttribute("aria-disabled", "false");
  await page.getByText("需要访问帮助？", { exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText(/请使用管理员授权的 ChatGPT 账号/)).toBeVisible();
  await context.setOffline(false);
  await action.click();
  await expect(page.getByRole("heading", { name: "Sites dispatcher sign-in" })).toBeVisible();
});

test("login image, light and dark themes, responsive layout and accessibility", async ({
  page,
}) => {
  for (const theme of ["light", "dark"]) {
    await page.addInitScript((value) => localStorage.setItem("openvigil-theme", value), theme);
    for (const width of [1440, 768, 414, 390, 375, 320]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/login");
      await expect(page.getByRole("link", { name: "使用 ChatGPT 登录" })).toBeVisible();
      await expect(page.getByText("风电智能运维平台", { exact: true })).toBeVisible();
      await expect(page.getByText(/陆上风电|陆上风场|海上风电|海上风场/)).toHaveCount(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
      await page.addScriptTag({ content: axeCore.source });
      const results = await page.evaluate(async () => {
        const axe = (window as unknown as { axe: typeof axeCore }).axe;
        return axe.run(document, {
          runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] },
        });
      });
      expect(results.violations).toEqual([]);
      if (width === 1440) {
        const hero = page.getByRole("img", { name: /AI 生成的风电场/ });
        await expect(hero).toBeVisible();
        await expect(hero).toHaveAttribute("src", "/images/login-onshore-wind-farm.png");
        expect(
          await hero.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 1000),
        ).toBe(true);
      }
      if (width === 1440 || width === 390) {
        await page.screenshot({
          path: `.artifacts/login/login-${theme}-${width}.png`,
          fullPage: true,
        });
      }
    }
  }
});
