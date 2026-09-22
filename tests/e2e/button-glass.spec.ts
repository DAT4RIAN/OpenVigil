import { expect, test } from "@playwright/test";
import axeCore from "axe-core";
import { fileURLToPath, pathToFileURL } from "node:url";

const previewPath = fileURLToPath(
  new URL("../../components/ui/Button.preview.html", import.meta.url),
);
const e2eBaseURL = process.env.OPENVIGIL_E2E_BASE_URL ?? "http://127.0.0.1:4179";

test("button glass material renders all eight states without losing accessibility", async ({
  browser,
}, testInfo) => {
  const context = await browser.newContext({
    viewport: { width: 720, height: 920 },
    reducedMotion: "reduce",
  });
  const page = await context.newPage();
  const client = await context.newCDPSession(page);

  try {
    await client.send("Emulation.setEmulatedMedia", {
      features: [
        { name: "prefers-reduced-motion", value: "reduce" },
        { name: "prefers-reduced-transparency", value: "no-preference" },
      ],
    });
    await page.goto(pathToFileURL(previewPath).href);
    await expect(page.locator(".preview-row button")).toHaveCount(8);

    const defaultButton = page.locator(".preview-row button").nth(0);
    const focusButton = page.locator(".is-focus");
    const activeButton = page.locator(".is-active");
    const disabledButton = page.locator("button:disabled").first();
    const loadingButton = page.locator('[data-state="loading"]');

    const material = await defaultButton.evaluate((element) => {
      const style = getComputedStyle(element);
      const edge = getComputedStyle(element, "::before");
      return {
        backdropFilter: style.backdropFilter,
        sheen: edge.backgroundImage,
        edgeWidth: edge.borderTopWidth,
        shadow: style.boxShadow,
      };
    });
    expect(material.backdropFilter).toContain("blur(12px)");
    expect(material.sheen).toContain("linear-gradient");
    expect(material.edgeWidth).toBe("1px");
    expect(material.shadow).not.toBe("none");

    await expect(focusButton).toHaveCSS("outline-style", "solid");
    await expect(focusButton).toHaveCSS("outline-width", "2px");
    await expect(activeButton).not.toHaveCSS("box-shadow", material.shadow);
    await expect(disabledButton).toHaveAttribute("disabled", "");
    await expect(disabledButton).toHaveCSS("cursor", "not-allowed");
    await expect(loadingButton).toHaveAttribute("aria-busy", "true");
    await expect(loadingButton).toBeDisabled();
    expect((await defaultButton.boundingBox())?.width).toBe(
      (await loadingButton.boundingBox())?.width,
    );

    for (const width of [320, 375, 414, 768]) {
      await page.setViewportSize({ width, height: 920 });
      const brokenLabels = await page.locator(".preview-row button").evaluateAll((buttons) =>
        buttons
          .filter((button) => {
            const bounds = button.getBoundingClientRect();
            const parent = button.parentElement?.getBoundingClientRect();
            return (
              getComputedStyle(button).whiteSpace !== "nowrap" ||
              button.scrollWidth > button.clientWidth + 1 ||
              (parent ? bounds.right > parent.right + 1 : false)
            );
          })
          .map((button) => button.textContent?.trim()),
      );
      expect(brokenLabels, `${width}px button labels`).toEqual([]);
    }

    await page.setViewportSize({ width: 720, height: 920 });
    await page.addScriptTag({ content: axeCore.source });
    const violations = await page.evaluate(async () => {
      const axe = (window as unknown as { axe: typeof axeCore }).axe;
      const { violations } = await axe.run(document, {
        runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] },
      });
      return violations
        .filter((item) => item.impact === "serious" || item.impact === "critical")
        .map((item) => item.id);
    });
    expect(violations).toEqual([]);

    await page.screenshot({
      path: testInfo.outputPath("button-glass-preview.png"),
      fullPage: true,
    });

    await client.send("Emulation.setEmulatedMedia", {
      features: [
        { name: "prefers-reduced-motion", value: "reduce" },
        { name: "prefers-reduced-transparency", value: "reduce" },
      ],
    });
    await expect(defaultButton).toHaveCSS("backdrop-filter", "none");
    await expect(defaultButton, "reduced transparency keeps an opaque primary fallback").toHaveCSS(
      "background-color",
      "rgb(23, 107, 117)",
    );
  } finally {
    await context.close();
  }
});

test("shared and native product buttons inherit the glass material in both themes", async ({
  browser,
}, testInfo) => {
  const context = await browser.newContext({
    baseURL: e2eBaseURL,
    viewport: { width: 1440, height: 900 },
    extraHTTPHeaders: { "x-e2e-runtime": "demo" },
  });
  const page = await context.newPage();
  const client = await context.newCDPSession(page);

  try {
    await client.send("Emulation.setEmulatedMedia", {
      features: [
        { name: "prefers-reduced-motion", value: "reduce" },
        { name: "prefers-reduced-transparency", value: "no-preference" },
      ],
    });
    await page.goto("/");

    for (const theme of ["light", "dark"] as const) {
      await page.evaluate((nextTheme) => localStorage.setItem("openvigil-theme", nextTheme), theme);
      await page.reload();
      await expect(page.locator("html")).toHaveAttribute("data-theme", theme);

      const controls = [
        page.getByRole("button", { name: "生成日报" }),
        page.locator(".segmented button").first(),
      ];
      for (const control of controls) {
        await expect(control).toBeVisible();
        const material = await control.evaluate((element) => ({
          backdropFilter: getComputedStyle(element).backdropFilter,
          sheen: getComputedStyle(element, "::before").backgroundImage,
          edge: getComputedStyle(element, "::before").borderTopWidth,
        }));
        expect(material.backdropFilter, `${theme} backdrop`).toContain("blur(12px)");
        expect(material.sheen, `${theme} sheen`).toContain("linear-gradient");
        expect(material.edge, `${theme} inner edge`).toBe("1px");
      }

      await page.addScriptTag({ content: axeCore.source });
      const violations = await page.evaluate(async () => {
        const axe = (window as unknown as { axe: typeof axeCore }).axe;
        const { violations } = await axe.run(document, {
          runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] },
        });
        return violations
          .filter((item) => item.impact === "serious" || item.impact === "critical")
          .map((item) => item.id);
      });
      expect(violations, `${theme} accessibility`).toEqual([]);

      await page.locator(".page-header").screenshot({
        path: testInfo.outputPath(`button-glass-${theme}.png`),
      });
    }

    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    const brokenMobileControls = await page
      .locator("button:visible, .button:visible")
      .evaluateAll((controls) =>
        controls
          .filter((control) => {
            const bounds = control.getBoundingClientRect();
            return (
              bounds.width < 43.5 ||
              bounds.height < 43.5 ||
              control.scrollWidth > control.clientWidth + 1
            );
          })
          .map((control) => control.getAttribute("aria-label") ?? control.textContent?.trim()),
      );
    expect(brokenMobileControls, "390px button touch targets and labels").toEqual([]);
  } finally {
    await context.close();
  }
});
