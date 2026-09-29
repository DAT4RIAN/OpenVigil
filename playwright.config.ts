import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.WINDOPS_E2E_PORT ?? "4179");

export default defineConfig({
  testDir: "./tests/e2e",
  testIgnore: [
    ...(process.env.WINDOPS_E2E_REAL_BACKEND === "1" ? [] : ["**/real-cross-layer.spec.ts"]),
    ...(process.env.WINDOPS_BUSINESS_E2E === "1" ? [] : ["**/business-cross-layer.spec.ts"]),
  ],
  outputDir: ".artifacts/playwright/test-results",
  fullyParallel: false,
  forbidOnly: true,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [
    ["line"],
    ["html", { outputFolder: ".artifacts/playwright/report", open: "never" }],
    ["./scripts/playwright-no-skips-reporter.mjs"],
  ],
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: {
    command: "node scripts/e2e-production-server.mjs",
    url: `http://127.0.0.1:${port}/__e2e/state`,
    reuseExistingServer: !process.env.CI && process.env.WINDOPS_BUSINESS_E2E !== "1",
    timeout: 30_000,
  },
  snapshotPathTemplate: "{testDir}/__screenshots__/{arg}{ext}",
});
