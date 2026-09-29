import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { readFile, readdir, mkdir, writeFile, rename } from "node:fs/promises";
import { cpus, platform, release, totalmem } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs, parseEnv } from "node:util";
import { chromium, expect } from "@playwright/test";
import { dataCounts, summarizeSamples } from "./performance-metrics.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const { values } = parseArgs({
  options: {
    report: { type: "string", default: ".artifacts/improvements/performance.json" },
    samples: { type: "string", default: "5" },
    "api-samples": { type: "string", default: "20" },
    "list-size": { type: "string", default: "2000" },
  },
});
function bounded(value, minimum, maximum) {
  const number = Number(value);
  if (!Number.isInteger(number) || number < minimum || number > maximum)
    throw new Error("Invalid benchmark size");
  return number;
}
const sampleCount = bounded(values.samples, 5, 30);
const apiSampleCount = bounded(values["api-samples"], 20, 100);
const listSize = bounded(values["list-size"], 100, 20000);
const reportPath = resolve(root, values.report);
const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");
async function treeDigest(folder) {
  const digest = createHash("sha256");
  async function visit(directory, prefix = "") {
    for (const entry of (await readdir(directory, { withFileTypes: true })).sort((a, b) =>
      a.name.localeCompare(b.name),
    )) {
      const name = `${prefix}${entry.name}`;
      if (entry.isDirectory()) await visit(join(directory, entry.name), `${name}/`);
      else if (entry.isFile())
        digest
          .update(name)
          .update("\0")
          .update(await readFile(join(directory, entry.name)))
          .update("\0");
      else throw new Error("Build contains an unsupported filesystem entry");
    }
  }
  await visit(folder);
  return digest.digest("hex");
}

const report = {
  schema: "openvigil.performance.v1",
  startedAt: new Date().toISOString(),
  boundary:
    "Local unthrottled Chromium lab measurements; Demo UI, synthetic large-list UI, and separately authenticated real FastAPI. Not field Web Vitals or production load acceptance.",
  environment: {
    platform: platform(),
    release: release(),
    cpu: cpus()[0]?.model,
    logicalCpus: cpus().length,
    memoryBytes: totalmem(),
    node: process.version,
    browser: null,
    cache: "new browser context per page sample; server and OS caches may be warm",
    cpuThrottling: 1,
    network: "loopback, no throttling",
    concurrency: 1,
  },
  inputs: { sampleCount, apiSampleCount, listSize },
  budgets: {
    fcpMs: 2500,
    readyMs: 4000,
    lcpAtReadyMs: 4000,
    interactionMs: 300,
    listFilterMs: 1000,
    apiMs: 500,
  },
  pages: [],
  lists: [],
  apis: [],
  errors: [],
  completed: false,
  passed: false,
};
async function save() {
  await mkdir(dirname(reportPath), { recursive: true });
  const temporary = `${reportPath}.tmp`;
  await writeFile(temporary, `${JSON.stringify(report, null, 2)}\n`);
  await rename(temporary, reportPath);
}
async function jsonRequest(origin, path, headers = {}) {
  const response = await fetch(new URL(path, origin), {
    headers,
    signal: AbortSignal.timeout(10000),
    redirect: "error",
  });
  if (!response.ok) throw new Error(`HTTP_${response.status}`);
  const bytes = await response.arrayBuffer();
  const payload = JSON.parse(Buffer.from(bytes).toString("utf8"));
  return { payload, bytes: bytes.byteLength };
}
// Only fixed diagnostics are emitted; no credential-bearing request or body is logged.
const errorCode = (error) => (/^HTTP_\d+$/.test(error.message) ? error.message : error.name);
async function painted(page) {
  await page.evaluate(
    () => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => done()))),
  );
}
async function instrument(page) {
  await page.addInitScript(() => {
    window.__ovPerf = { lcpAtReadyMs: null, longTaskCount: 0, longTaskMs: 0, clsAtReady: 0 };
    for (const type of ["largest-contentful-paint", "longtask", "layout-shift"]) {
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (type === "largest-contentful-paint") window.__ovPerf.lcpAtReadyMs = entry.startTime;
          if (type === "longtask") {
            window.__ovPerf.longTaskCount++;
            window.__ovPerf.longTaskMs += entry.duration;
          }
          if (type === "layout-shift" && !entry.hadRecentInput)
            window.__ovPerf.clsAtReady += entry.value;
        }
      }).observe({ type, buffered: true });
    }
  });
}
async function metrics(page) {
  await painted(page);
  return page.evaluate(() => ({
    ...window.__ovPerf,
    readyMs: performance.now(),
    fcpMs: performance.getEntriesByName("first-contentful-paint")[0]?.startTime ?? null,
    domRows: document.querySelectorAll("tbody tr").length,
  }));
}
function captureNetworkFailures(page, sample) {
  sample.networkErrors = [];
  sample.cancelledRequests = 0;
  page.on("requestfailed", (request) => {
    const reason = request.failure()?.errorText;
    if (reason === "net::ERR_ABORTED") sample.cancelledRequests++;
    else sample.networkErrors.push({ path: new URL(request.url()).pathname, reason });
  });
}
async function interaction(page, action, target) {
  await page.evaluate(({ selector, text, enabled, expectedRows, eventType = "click" }) => {
    const state = (window.__ovInteraction = { start: null, end: null, scheduled: false });
    const check = () => {
      const element = document.querySelector(selector);
      if (state.start === null || state.scheduled || !element || !element.getClientRects().length)
        return;
      if (text && !element.textContent.includes(text)) return;
      if (enabled && element.disabled) return;
      if (
        expectedRows !== undefined &&
        document.querySelectorAll("tbody tr").length !== expectedRows
      )
        return;
      state.scheduled = true;
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          state.end = performance.now();
          observer.disconnect();
          document.removeEventListener(eventType, started, true);
        }),
      );
    };
    const started = () => {
      if (state.start === null) state.start = performance.now();
      check();
    };
    const observer = new MutationObserver(check);
    observer.observe(document.body, {
      childList: true,
      attributes: true,
      characterData: true,
      subtree: true,
    });
    document.addEventListener(eventType, started, true);
  }, target);
  await action();
  await page.waitForFunction(() => window.__ovInteraction.end !== null, null, { timeout: 10000 });
  return page.evaluate(() => window.__ovInteraction.end - window.__ovInteraction.start);
}

let browser;
try {
  const folder = join(root, ".artifacts/local-stack");
  const config = JSON.parse(await readFile(join(folder, "configuration.json"), "utf8"));
  if (resolve(config.root) !== root) throw new Error("Local stack belongs to a different checkout");
  const frontend = `http://127.0.0.1:${bounded(config.frontend_port, 1024, 65535)}`;
  const backend = `http://127.0.0.1:${bounded(config.api_port, 1024, 65535)}`;
  const privateEnv = parseEnv(await readFile(join(folder, ".env.runtime"), "utf8"));
  if (
    privateEnv.WINDOPS_ENVIRONMENT !== "development" ||
    privateEnv.WINDOPS_AUTH_MODE !== "static_tokens" ||
    !privateEnv.WINDOPS_OPERATIONS_MANAGER_API_KEY
  )
    throw new Error("Expected isolated development authentication");
  const headers = { Authorization: `Bearer ${privateEnv.WINDOPS_OPERATIONS_MANAGER_API_KEY}` };
  report.identity = {
    commit: execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim(),
    dirty: Boolean(
      execFileSync("git", ["status", "--porcelain"], { cwd: root, encoding: "utf8" }).trim(),
    ),
    buildSha256: await treeDigest(join(root, "dist")),
    runnerSha256: sha256(await readFile(fileURLToPath(import.meta.url))),
    metricsSha256: sha256(await readFile(join(root, "scripts/performance-metrics.mjs"))),
    frontend,
    backend,
    project: config.project,
  };
  const runtime = (await jsonRequest(frontend, "/api/runtime")).payload.data;
  if (runtime.runtimeMode !== "demo")
    throw new Error("Synthetic list benchmark is restricted to Demo");
  report.runtimeMode = runtime.runtimeMode;
  report.demoData = {};
  for (const path of ["/api/turbines", "/api/diagnoses", "/api/predictive-assessments"]) {
    const result = await jsonRequest(frontend, path);
    report.demoData[path] = {
      counts: dataCounts(result.payload),
      bytes: result.bytes,
      declaredTotal: result.payload.meta?.total ?? null,
    };
  }
  await jsonRequest(backend, "/api/v1/readyz", headers);
  browser = await chromium.launch();
  report.environment.browser = browser.version();
  const routes = [
    { path: "/", ready: ".page-header h1" },
    { path: "/diagnosis", ready: "h2", text: "机组诊断记录" },
    { path: "/predictive-maintenance", ready: 'section[aria-label="模型说明"]' },
  ];
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 390, height: 844 },
  ]) {
    for (const route of routes) {
      const group = { path: route.path, viewport, samples: [], summary: {} };
      report.pages.push(group);
      for (let index = 0; index < sampleCount; index++) {
        const context = await browser.newContext({ viewport, serviceWorkers: "block" });
        const page = await context.newPage();
        page.setDefaultTimeout(10000);
        const sample = { index, error: null, phase: "navigation", httpErrors: [], pageErrors: [] };
        group.samples.push(sample);
        captureNetworkFailures(page, sample);
        page.on("pageerror", (error) => sample.pageErrors.push(error.name));
        page.on("response", (response) => {
          if (response.status() >= 400)
            sample.httpErrors.push({
              path: new URL(response.url()).pathname,
              status: response.status(),
            });
        });
        try {
          await instrument(page);
          const response = await page.goto(`${frontend}${route.path}`, {
            waitUntil: "domcontentloaded",
          });
          if (response.status() !== 200) throw new Error(`HTTP_${response.status()}`);
          sample.phase = "content-ready";
          await expect(
            page
              .locator(route.ready)
              .filter(route.text ? { hasText: route.text } : {})
              .first(),
          ).toBeVisible();
          Object.assign(sample, await metrics(page));
          sample.phase = "search-interaction";
          sample.interactionMs = await interaction(
            page,
            () => page.getByRole("button", { name: "打开全局搜索" }).click(),
            { selector: ".command-dialog" },
          );
          await expect(page.locator(".command-dialog input")).toBeFocused();
          if (sample.httpErrors.length || sample.pageErrors.length || sample.networkErrors.length)
            throw new Error("PageRuntimeFailure");
          sample.phase = "complete";
        } catch (error) {
          sample.error = errorCode(error);
        } finally {
          page.removeAllListeners();
          await context.close();
        }
      }
      for (const metric of ["fcpMs", "readyMs", "lcpAtReadyMs", "interactionMs"]) {
        group.summary[metric] = summarizeSamples(
          group.samples,
          metric,
          report.budgets[metric],
          sampleCount,
        );
      }
      await save();
      console.log(`Measured ${route.path} at ${viewport.width}px`);
    }
  }
  const templateResponse = await jsonRequest(frontend, "/api/alarms");
  const template = templateResponse.payload;
  if (!Array.isArray(template.data) || !template.data.length)
    throw new Error("Alarm template missing");
  const synthetic = {
    ...template,
    data: Array.from({ length: listSize }, (_, index) => ({
      ...template.data[index % template.data.length],
      id: `PERF-${String(index).padStart(6, "0")}`,
      turbineId: `WT-PERF-${String(index).padStart(6, "0")}`,
      missionId: null,
    })),
    meta: { ...template.meta, total: listSize, syntheticPerformanceData: true },
  };
  const body = JSON.stringify(synthetic);
  const group = {
    dataSource: "synthetic cloned Demo alarm schema; browser interception only",
    preparation:
      "Wait 31 real seconds for the existing Demo query cache to become stale, then reconnect. Preparation is excluded from refresh-to-painted latency; browser clocks are unchanged.",
    dataRows: listSize,
    dataBytes: Buffer.byteLength(body),
    datasetSha256: sha256(body),
    viewport: { width: 1440, height: 900 },
    samples: [],
    summary: {},
  };
  report.lists.push(group);
  for (let index = 0; index < sampleCount; index++) {
    const context = await browser.newContext({ viewport: group.viewport, serviceWorkers: "block" });
    const page = await context.newPage();
    page.setDefaultTimeout(10000);
    const sample = { index, error: null, phase: "navigation", pageErrors: [], httpErrors: [] };
    group.samples.push(sample);
    captureNetworkFailures(page, sample);
    page.on("pageerror", (error) => sample.pageErrors.push(error.name));
    page.on("response", (response) => {
      if (response.status() >= 400)
        sample.httpErrors.push({
          path: new URL(response.url()).pathname,
          status: response.status(),
        });
    });
    try {
      await instrument(page);
      await page.route("**/api/alarms", (route) =>
        route.fulfill({ status: 200, contentType: "application/json", body }),
      );
      const response = await page.goto(`${frontend}/alarms`, { waitUntil: "domcontentloaded" });
      if (response.status() !== 200) throw new Error(`HTTP_${response.status()}`);
      await expect(page.getByRole("searchbox", { name: "搜索表格" })).toBeVisible();
      sample.phase = "wait-for-stale-demo-cache";
      // Use elapsed real time, not clock mocks that could invalidate performance measurements.
      await page.waitForTimeout(31000);
      sample.phase = "refresh-large-list";
      const started = await page.evaluate(() => {
        const start = performance.now();
        window.dispatchEvent(new Event("offline"));
        window.dispatchEvent(new Event("online"));
        return start;
      });
      await expect(
        page.locator('[aria-live="polite"]').filter({ hasText: `${listSize} 条记录` }),
      ).toBeVisible({ timeout: 10000 });
      Object.assign(sample, await metrics(page));
      sample.readyMs -= started;
      sample.phase = "pagination";
      sample.paginationMs = await interaction(
        page,
        () => page.getByRole("button", { name: "下一页", exact: true }).click(),
        { selector: '[aria-label="上一页"]', enabled: true },
      );
      sample.phase = "filter";
      const target = `PERF-${String(listSize - 1).padStart(6, "0")}`;
      sample.listFilterMs = await interaction(
        page,
        () => page.getByRole("searchbox", { name: "搜索表格" }).fill(`WT-${target}`),
        { selector: `[aria-label="选择记录 ${target}"]`, eventType: "input", expectedRows: 1 },
      );
      await expect(page.locator("tbody tr")).toHaveCount(1);
      await expect(
        page.locator('[aria-live="polite"]').filter({ hasText: /^1 条记录/ }),
      ).toBeVisible();
      if (sample.pageErrors.length || sample.httpErrors.length || sample.networkErrors.length)
        throw new Error("PageRuntimeFailure");
      sample.phase = "complete";
    } catch (error) {
      sample.error = errorCode(error);
    } finally {
      page.removeAllListeners();
      await context.close();
    }
    await save();
    console.log(`Large-list sample ${index + 1}/${sampleCount}: ${sample.error ?? "measured"}`);
  }
  group.summary.readyMs = summarizeSamples(
    group.samples,
    "readyMs",
    report.budgets.readyMs,
    sampleCount,
  );
  group.summary.paginationMs = summarizeSamples(
    group.samples,
    "paginationMs",
    report.budgets.interactionMs,
    sampleCount,
  );
  group.summary.listFilterMs = summarizeSamples(
    group.samples,
    "listFilterMs",
    report.budgets.listFilterMs,
    sampleCount,
  );
  await save();
  console.log(`Measured synthetic ${listSize}-row alarm table`);
  for (const path of ["/api/v1/catalog", "/api/v1/turbines", "/api/v1/data-catalog"]) {
    const collectionKeys = path.endsWith("/catalog")
      ? ["agents", "skills", "tools"]
      : path.endsWith("/turbines")
        ? ["turbines", "wind_farms"]
        : undefined;
    const group = {
      path,
      dataSource: "authenticated real local FastAPI; no interception",
      warmup: null,
      samples: [],
      summary: {},
    };
    report.apis.push(group);
    for (let index = -1; index < apiSampleCount; index++) {
      const sample = { index, error: null };
      const started = performance.now();
      try {
        const result = await jsonRequest(backend, path, headers);
        sample.dataCounts = dataCounts(result.payload, collectionKeys);
        sample.bytes = result.bytes;
      } catch (error) {
        sample.error = errorCode(error);
      }
      sample.durationMs = performance.now() - started;
      if (index === -1) group.warmup = sample;
      else group.samples.push(sample);
    }
    group.summary = summarizeSamples(
      group.samples,
      "durationMs",
      report.budgets.apiMs,
      apiSampleCount,
    );
    await save();
    console.log(`Measured ${path}`);
  }
  report.completed = true;
  report.passed =
    [...report.pages, ...report.lists].every((group) =>
      Object.values(group.summary).every((metric) => metric.passed),
    ) && report.apis.every((group) => group.summary.passed && !group.warmup.error);
} catch (error) {
  report.errors.push(errorCode(error));
} finally {
  if (browser) await browser.close();
  report.finishedAt = new Date().toISOString();
  await save();
}
console.log(
  JSON.stringify({
    report: reportPath,
    completed: report.completed,
    passed: report.passed,
    errors: report.errors,
  }),
);
if (!report.passed) process.exitCode = 1;
