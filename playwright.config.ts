import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  testIgnore: process.env.WINDOPS_E2E_REAL_BACKEND === "1" ? [] : ["**/real-cross-layer.spec.ts"],
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
    baseURL: "http://127.0.0.1:4179",
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
    url: "http://127.0.0.1:4179/__e2e/state",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
  snapshotPathTemplate: "{testDir}/__screenshots__/{arg}{ext}",
});
