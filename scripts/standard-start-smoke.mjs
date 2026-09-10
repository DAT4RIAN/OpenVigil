import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { once } from "node:events";
import { createServer } from "node:net";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";

const workspaceRoot = fileURLToPath(new URL("..", import.meta.url));
const origin = "http://127.0.0.1:3000";
const startupTimeoutMs = 45_000;
const runtimeKeys = [
  "WINDOPS_RUNTIME_MODE",
  "WINDOPS_BACKEND_BASE_URL",
  "WINDOPS_BACKEND_AUTH_MODE",
  "WINDOPS_BACKEND_API_TOKEN",
  "WINDOPS_BACKEND_DELEGATION_SECRET",
  "WINDOPS_BACKEND_REQUEST_TIMEOUT_MS",
  "WINDOPS_BACKEND_EXPECTED_RELEASE_ID",
  "WINDOPS_BACKEND_EXPECTED_IMAGE_DIGEST",
];

function isolatedEnvironment(overrides = {}) {
  const environment = { ...process.env, NO_COLOR: "1" };
  for (const key of runtimeKeys) delete environment[key];
  return { ...environment, ...overrides };
}

async function assertPortAvailable() {
  const server = createServer();
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(3000, "127.0.0.1", resolve);
  });
  await new Promise((resolve, reject) => {
    server.close((error) => (error ? reject(error) : resolve()));
  });
}

function startServer(environment) {
  const windows = process.platform === "win32";
  const executable = windows ? (process.env.ComSpec ?? "cmd.exe") : "pnpm";
  const arguments_ = windows ? ["/d", "/s", "/c", "pnpm start"] : ["start"];
  const child = spawn(executable, arguments_, {
    cwd: workspaceRoot,
    env: environment,
    detached: !windows,
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
  let output = "";
  let spawnError = null;
  const capture = (chunk) => {
    output = `${output}${chunk}`.slice(-32_000);
  };
  child.stdout.on("data", capture);
  child.stderr.on("data", capture);
  child.on("error", (error) => {
    spawnError = error;
  });
  return { child, output: () => output, spawnError: () => spawnError };
}

async function requestWhenReady(server, path) {
  const deadline = Date.now() + startupTimeoutMs;
  while (Date.now() < deadline) {
    if (server.spawnError()) throw server.spawnError();
    if (server.child.exitCode !== null || server.child.signalCode !== null) {
      throw new Error(`pnpm start exited before readiness:\n${server.output()}`);
    }
    try {
      return await fetch(`${origin}${path}`, { signal: AbortSignal.timeout(2_000) });
    } catch {
      await delay(200);
    }
  }
  throw new Error(
    `pnpm start did not become ready within ${startupTimeoutMs} ms:\n${server.output()}`,
  );
}

async function stopServer(server) {
  const { child } = server;
  if (child.exitCode !== null || child.signalCode !== null || child.pid === undefined) return;
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], {
      stdio: "ignore",
      windowsHide: true,
    });
  } else {
    try {
      process.kill(-child.pid, "SIGTERM");
    } catch (error) {
      if (error.code !== "ESRCH") throw error;
    }
  }
  await Promise.race([once(child, "exit"), delay(5_000)]);
  if (child.exitCode === null && child.signalCode === null && process.platform !== "win32") {
    try {
      process.kill(-child.pid, "SIGKILL");
    } catch (error) {
      if (error.code !== "ESRCH") throw error;
    }
    await Promise.race([once(child, "exit"), delay(5_000)]);
  }
}

async function demoSmoke() {
  await assertPortAvailable();
  const server = startServer(isolatedEnvironment());
  try {
    const runtimeResponse = await requestWhenReady(server, "/api/runtime");
    assert.equal(runtimeResponse.status, 200);
    assert.match(runtimeResponse.headers.get("content-type") ?? "", /^application\/json/);
    const runtime = await runtimeResponse.json();
    assert.equal(runtime.data.runtimeMode, "demo");
    assert.equal(runtime.data.fixtureFallbackAllowed, true);
    assert.equal(runtime.error, null);

    const rootResponse = await fetch(`${origin}/`, { signal: AbortSignal.timeout(10_000) });
    assert.equal(rootResponse.status, 200);
    assert.match(rootResponse.headers.get("content-type") ?? "", /^text\/html/);
    assert.match(await rootResponse.text(), /WindOps/);
  } finally {
    await stopServer(server);
  }
}

async function invalidProductionSmoke() {
  await assertPortAvailable();
  const server = startServer(isolatedEnvironment({ WINDOPS_RUNTIME_MODE: "production" }));
  try {
    const runtimeResponse = await requestWhenReady(server, "/api/runtime");
    assert.equal(runtimeResponse.status, 500);
    assert.match(runtimeResponse.headers.get("content-type") ?? "", /^application\/json/);
    const runtime = await runtimeResponse.json();
    assert.equal(runtime.data, null);
    assert.equal(runtime.error.code, "INVALID_DELEGATION_SECRET");
    assert.equal(runtime.meta.runtimeMode, "production");
    assert.equal(runtime.meta.fixtureFallback, false);

    const rootResponse = await fetch(`${origin}/`, { signal: AbortSignal.timeout(10_000) });
    assert.equal(rootResponse.status, 500);
    assert.match(rootResponse.headers.get("content-type") ?? "", /^application\/json/);
    const root = await rootResponse.json();
    assert.equal(root.error.code, "INVALID_DELEGATION_SECRET");
    assert.doesNotMatch(JSON.stringify(root), /Cannot read properties|TypeError|stack/i);
  } finally {
    await stopServer(server);
  }
}

await demoSmoke();
await invalidProductionSmoke();
await assertPortAvailable();
console.log("standard pnpm start smoke passed (demo + invalid production fail-closed)");
