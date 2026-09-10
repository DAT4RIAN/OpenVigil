import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  PREDICTIVE_ASSESSMENT_RUN_TIMEOUT_MS,
  isAllowedProductionGatewayPath,
  isAllowedProductionGatewayRequest,
  probeProductionBackend,
  proxyProductionBackendRequest,
  productionBackendRequestTimeoutMs,
  requireProductionBackend,
} from "../lib/production-runtime.ts";
import {
  productionAlarmsResponse,
  productionDecisionsResponse,
  productionHealthAssessmentsResponse,
  productionMissionsResponse,
  productionResourcesResponse,
  productionScadaHistoryResponse,
  productionScadaMeasurementsResponse,
  productionTurbinesResponse,
  productionWorkOrdersResponse,
} from "../lib/production-domain-adapter.ts";
import { runWithWorkerEnv } from "../lib/worker-env.ts";

const workerUrl = new URL("../dist/server/index.js", import.meta.url);
workerUrl.searchParams.set("production-runtime-test", `${process.pid}-${Date.now()}`);
const { default: worker } = await import(workerUrl.href);

const context = {
  waitUntil() {},
  passThroughOnException() {},
};

const baseEnvironment = {
  ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) },
};
const delegationSecret = "worker-delegation-secret-with-at-least-forty-eight-characters";
const expectedReleaseId = "windops-2026.08.14-rc1";
const expectedCommitSha = "a".repeat(40);
const expectedImageDigest = `sha256:${"b".repeat(64)}`;

function backendJson(body, init = {}) {
  const headers = new Headers(init.headers);
  headers.set("x-windops-release-id", expectedReleaseId);
  headers.set("x-windops-commit-sha", expectedCommitSha);
  headers.set("x-windops-image-digest", expectedImageDigest);
  return Response.json(body, { ...init, headers });
}

const productionEnvironment = {
  ...baseEnvironment,
  WINDOPS_RUNTIME_MODE: "production",
  WINDOPS_BACKEND_BASE_URL: "https://windops-backend.example",
  WINDOPS_BACKEND_AUTH_MODE: "sites_delegation",
  WINDOPS_BACKEND_DELEGATION_SECRET: delegationSecret,
  WINDOPS_BACKEND_REQUEST_TIMEOUT_MS: "5000",
  WINDOPS_BACKEND_EXPECTED_RELEASE_ID: expectedReleaseId,
  WINDOPS_BACKEND_EXPECTED_IMAGE_DIGEST: expectedImageDigest,
};

const managerCapabilities = [
  "agent.manage",
  "alarm.command",
  "mission.comment",
  "mission.create",
  "mission.escalate",
  "model.manage",
  "platform.manage",
  "report.generate",
  "resource.manage",
  "view.agents",
  "view.alarms",
  "view.assets",
  "view.dashboard",
  "view.decisions",
  "view.knowledge",
  "view.missions",
  "view.models",
  "view.platform",
  "view.reports",
  "view.resources",
  "view.telemetry",
  "view.work_orders",
  "work_order.schedule",
];

function identitySession(capabilities = managerCapabilities, roles = ["operations_manager"]) {
  return {
    subject: "sites-user-42",
    email: "operator@example.com",
    roles,
    capabilities,
    scope: {
      tenant_count: 1,
      wind_farm_count: 0,
      turbine_count: 0,
      entity_count: 0,
      allow_global: true,
    },
  };
}

const platformFetch = globalThis.fetch;
globalThis.fetch = async (input, init) => {
  if (String(input) === "https://windops-backend.example/api/v1/session") {
    return backendJson(identitySession());
  }
  return platformFetch(input, init);
};

test("predictive inference uses the explicit gateway timeout contract", () => {
  assert.equal(PREDICTIVE_ASSESSMENT_RUN_TIMEOUT_MS, 30_000);
  assert.equal(
    productionBackendRequestTimeoutMs("/api/v1/predictive-assessments/run", 8_000),
    30_000,
  );
  assert.equal(productionBackendRequestTimeoutMs("/api/v1/turbines", 8_000), 8_000);
});

test("rotation confirmation is method-scoped at the production gateway", () => {
  const path = "/api/v1/platform/configuration-security-audits/audit-42/rotation-confirmation";
  assert.equal(isAllowedProductionGatewayPath(path), true);
  assert.equal(isAllowedProductionGatewayRequest("POST", path), true);
  assert.equal(isAllowedProductionGatewayRequest("GET", path), false);
  assert.equal(isAllowedProductionGatewayRequest("DELETE", path), false);
});

test("governed benchmark reads are explicitly allowed by the production gateway", () => {
  for (const path of [
    "/api/v1/benchmarks/datasets",
    "/api/v1/benchmarks/datasets/care-v6/events",
    "/api/v1/benchmarks/evaluations",
    "/api/v1/benchmarks/evaluations/care-eval/results",
    "/api/v1/benchmarks/diagnoses",
    "/api/v1/benchmarks/replay-runs/h5a00001/curve",
  ]) {
    assert.equal(isAllowedProductionGatewayPath(path), true, path);
    assert.equal(isAllowedProductionGatewayRequest("GET", path), true, path);
  }
  assert.equal(isAllowedProductionGatewayPath("/api/v1/benchmarks/raw.csv"), false);
  assert.equal(isAllowedProductionGatewayPath("/api/v1/benchmarks/datasets/care-v6/raw"), false);
  const exportPath = "/api/v1/benchmarks/evaluations/care-eval/exports";
  assert.equal(isAllowedProductionGatewayPath(exportPath), true);
  assert.equal(isAllowedProductionGatewayRequest("POST", exportPath), true);
  assert.equal(isAllowedProductionGatewayRequest("GET", exportPath), false);
  assert.equal(isAllowedProductionGatewayRequest("DELETE", exportPath), false);
});

function sitesRequest(url, init = {}) {
  const headers = new Headers(init.headers);
  headers.set("oai-authenticated-user-id", "sites-user-42");
  headers.set("oai-authenticated-user-email", "operator@example.com");
  return new Request(url, { ...init, headers });
}

function fetchWorker(path, environment = productionEnvironment, init = {}) {
  const url = new URL(path, "https://windops.example");
  const headers = new Headers(init.headers);
  if (!url.pathname.startsWith("/api/") && !url.pathname.startsWith("/ws/")) {
    headers.set("oai-authenticated-user-id", "sites-user-42");
    headers.set("oai-authenticated-user-email", "operator@example.com");
  }
  return worker.fetch(new Request(url, { ...init, headers }), environment, context);
}

test("CI directly executes the standard pnpm start smoke", async () => {
  const packageJson = JSON.parse(
    await readFile(new URL("../package.json", import.meta.url), "utf8"),
  );
  assert.equal(packageJson.scripts["test:start-smoke"], "node scripts/standard-start-smoke.mjs");
  const workflow = await readFile(new URL("../.github/workflows/ci.yml", import.meta.url), "utf8");
  assert.match(workflow, /run: pnpm build && pnpm test:start-smoke/);
  const smoke = await readFile(
    new URL("../scripts/standard-start-smoke.mjs", import.meta.url),
    "utf8",
  );
  assert.match(smoke, /spawn\(executable, arguments_/);
  assert.match(smoke, /"pnpm start"/);
  assert.match(smoke, /INVALID_DELEGATION_SECRET/);
  assert.match(smoke, /taskkill/);
  assert.match(smoke, /SIGTERM/);
  const workerEntry = await readFile(new URL("../worker/index.ts", import.meta.url), "utf8");
  assert.match(workerEntry, /env: Env \| undefined/);
  assert.match(workerEntry, /const runtimeEnv = normalizeWorkerEnv\(env\)/);
});

test("production documents authenticate and authorize before rendering business data", async () => {
  const anonymous = await worker.fetch(
    new Request("https://windops.example/missions?status=open"),
    productionEnvironment,
    context,
  );
  assert.equal(anonymous.status, 302);
  assert.equal(new URL(anonymous.headers.get("location")).pathname, "/signin-with-chatgpt");
  assert.equal(
    new URL(anonymous.headers.get("location")).searchParams.get("return_to"),
    "/missions?status=open",
  );

  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input) => {
    if (String(input).endsWith("/api/v1/session")) {
      return backendJson(
        { error: { code: "FORBIDDEN", message: "No WindOps role is assigned" } },
        { status: 403 },
      );
    }
    throw new Error(`unexpected request ${String(input)}`);
  };
  try {
    const forbidden = await fetchWorker("/settings");
    assert.equal(forbidden.status, 403);
    const html = await forbidden.text();
    assert.match(html, /当前账号没有 WindOps 访问权限/);
    assert.match(html, /No WindOps role is assigned/);
    assert.doesNotMatch(html, /创建配置修订/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("production shell trusts backend capabilities and discards client capability spoofing", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input) => {
    if (String(input).endsWith("/api/v1/session")) {
      return backendJson(
        identitySession(
          ["mission.comment", "view.missions", "view.platform", "view.work_orders"],
          ["field_technician"],
        ),
      );
    }
    throw new Error(`unexpected request ${String(input)}`);
  };
  try {
    const response = await fetchWorker("/settings", productionEnvironment, {
      headers: {
        "x-windops-trusted-session": "forged-manager-session",
        "x-windops-capabilities": "platform.manage,model.manage",
      },
    });
    assert.equal(response.status, 200);
    const html = await response.text();
    assert.match(html, /field_technician/);
    assert.match(html, /Sites 委托身份/);
    assert.match(html, /创建配置修订需要运维经理和全局平台授权/);
    assert.match(html, /安全退出 WindOps/);
    assert.doesNotMatch(html, /operations_manager/);
    assert.doesNotMatch(html, /href="\/models"/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("production mode fails closed instead of serving fixture APIs and simulated sockets", async () => {
  const apiResponse = await fetchWorker("/api/evidence");
  assert.equal(apiResponse.status, 503);
  const apiBody = await apiResponse.json();
  assert.equal(apiBody.error.code, "PRODUCTION_ROUTE_NOT_MIGRATED");
  assert.equal(apiBody.meta.fixtureFallback, false);
  assert.equal(apiResponse.headers.get("x-content-type-options"), "nosniff");
  assert.equal(apiResponse.headers.get("x-frame-options"), "DENY");
  assert.equal(apiResponse.headers.get("referrer-policy"), "no-referrer");
  assert.match(apiResponse.headers.get("content-security-policy"), /frame-ancestors 'none'/);
  assert.equal(
    apiResponse.headers.get("strict-transport-security"),
    "max-age=63072000; includeSubDomains; preload",
  );

  const socketResponse = await fetchWorker("/ws/scada", productionEnvironment, {
    headers: { upgrade: "websocket" },
  });
  assert.equal(socketResponse.status, 503);
  const socketBody = await socketResponse.json();
  assert.equal(socketBody.error.code, "PRODUCTION_REALTIME_NOT_MIGRATED");
});

test("production mode rejects insecure or example backend configuration", async () => {
  const insecure = await fetchWorker("/api/runtime", {
    ...productionEnvironment,
    WINDOPS_BACKEND_BASE_URL: "http://backend.internal:8000",
  });
  assert.equal(insecure.status, 500);
  assert.equal((await insecure.json()).error.code, "INSECURE_BACKEND_URL");

  const serviceTokenMode = await fetchWorker("/api/runtime", {
    ...productionEnvironment,
    WINDOPS_BACKEND_AUTH_MODE: "service_token",
    WINDOPS_BACKEND_API_TOKEN: "replace-with-a-configured-windops-role-token",
  });
  assert.equal(serviceTokenMode.status, 500);
  assert.equal((await serviceTokenMode.json()).error.code, "INSECURE_BACKEND_AUTH_MODE");

  const exampleDelegation = await fetchWorker("/api/runtime", {
    ...productionEnvironment,
    WINDOPS_BACKEND_DELEGATION_SECRET: "replace-with-a-gateway-secret",
  });
  assert.equal(exampleDelegation.status, 500);
  assert.equal((await exampleDelegation.json()).error.code, "INVALID_DELEGATION_SECRET");

  const missingRelease = await fetchWorker("/api/runtime", {
    ...productionEnvironment,
    WINDOPS_BACKEND_EXPECTED_RELEASE_ID: undefined,
  });
  assert.equal(missingRelease.status, 500);
  assert.equal((await missingRelease.json()).error.code, "INVALID_EXPECTED_RELEASE_ID");

  const placeholderDigest = await fetchWorker("/api/runtime", {
    ...productionEnvironment,
    WINDOPS_BACKEND_EXPECTED_IMAGE_DIGEST: `sha256:${"0".repeat(64)}`,
  });
  assert.equal(placeholderDigest.status, 500);
  assert.equal((await placeholderDigest.json()).error.code, "INVALID_EXPECTED_IMAGE_DIGEST");
});

test("production shell and settings never render fixture operations state", async () => {
  const response = await fetchWorker("/settings");
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /WindOps Production/);
  assert.match(html, /PostgreSQL/);
  assert.match(html, /持久事件通道/);
  assert.doesNotMatch(html, /D1 工作流/);
  assert.doesNotMatch(html, /WebSocket 通道/);
  assert.doesNotMatch(html, /确定性演示数据流/);
  assert.doesNotMatch(
    html,
    /本地演示运行中|SCADA 快照|D1 · R|WT-023 闭环|主轴承振动告警升级|下一窗口|林工/,
  );
  assert.match(html, /生产运行模式/);
  assert.match(html, /PostgreSQL \/ TimescaleDB 权威数据/);
  assert.match(html, /Sites 委托身份/);
});

test("every production workspace receives the production shell contract", async () => {
  const paths = [
    "/",
    "/agents",
    "/alarms",
    "/data",
    "/decisions",
    "/diagnosis",
    "/digital-twin",
    "/health",
    "/knowledge",
    "/knowledge-graph",
    "/maintenance",
    "/missions",
    "/missions/MISSION-RELEASE-VERIFY",
    "/models",
    "/predictive-maintenance",
    "/reports",
    "/resources",
    "/scada",
    "/settings",
    "/turbines/WT-RELEASE-VERIFY",
    "/wind-farms",
    "/work-orders",
  ];
  for (const path of paths) {
    const response = await fetchWorker(path);
    assert.equal(response.status, 200, `${path} did not render`);
    const html = await response.text();
    assert.match(html, /生产运行模式/, `${path} did not receive the production shell`);
    assert.match(html, /Sites 委托身份/, `${path} did not expose the production identity mode`);
    assert.doesNotMatch(
      html,
      /本地演示运行中|SCADA 快照|D1 · R|WT-023 闭环|主轴承振动告警升级|下一窗口|林工/,
      `${path} leaked fixture shell state`,
    );
  }
});

test("production workspace shells never leak fixture drawer, approval, summary, or diagnosis data", async () => {
  const missionsResponse = await fetchWorker("/missions");
  assert.equal(missionsResponse.status, 200);
  const missionsHtml = await missionsResponse.text();
  assert.match(missionsHtml, /生产运行模式/);
  // F3: 生产汇总区统计真实 Mission 数据；无已闭环 Mission 时显式空态。
  assert.doesNotMatch(missionsHtml, /4h 18m/);
  assert.doesNotMatch(missionsHtml, /较 7 日均值/);
  assert.match(missionsHtml, /暂无已闭环 Mission，无法计算/);

  const diagnosisResponse = await fetchWorker("/diagnosis");
  assert.equal(diagnosisResponse.status, 200);
  const diagnosisHtml = await diagnosisResponse.text();
  // F4: 生产页头不硬链 fixture Mission，初始模型声明不携带 fixture 诊断元数据。
  assert.doesNotMatch(diagnosisHtml, /查看 WT-023 Mission/);
  assert.doesNotMatch(diagnosisHtml, /MISSION-2026-0823/);
  assert.doesNotMatch(diagnosisHtml, /仅供产品演示；不会调用真实模型/);
  assert.match(diagnosisHtml, /正在读取生产诊断模型元数据/);

  const decisionsResponse = await fetchWorker("/decisions");
  assert.equal(decisionsResponse.status, 200);
  const decisionsHtml = await decisionsResponse.text();
  // F2: 生产审批意见初始为空，演示审批文案不进入生产页面。
  assert.doesNotMatch(decisionsHtml, /同意执行方案 B/);

  const alarmsResponse = await fetchWorker("/alarms");
  assert.equal(alarmsResponse.status, 200);
  const alarmsHtml = await alarmsResponse.text();
  // F1: 生产告警中心不渲染"主轴承早期退化"演示诊断卡。
  assert.doesNotMatch(alarmsHtml, /主轴承早期退化/);
});

test("runtime readiness probes the Python backend without exposing configuration secrets", async () => {
  const originalFetch = globalThis.fetch;
  let observedUrl = "";
  let observedAuthorization = "";
  globalThis.fetch = async (input, init) => {
    observedUrl = String(input);
    observedAuthorization = new Headers(init?.headers).get("authorization") ?? "";
    return backendJson({
      status: "ready",
      release: {
        release_id: expectedReleaseId,
        commit_sha: expectedCommitSha,
        image_digest: expectedImageDigest,
      },
    });
  };
  try {
    const backend = await runWithWorkerEnv(productionEnvironment, () => probeProductionBackend());
    const config = runWithWorkerEnv(productionEnvironment, () => requireProductionBackend());
    assert.equal(config.mode, "production");
    assert.equal(backend.configured, true);
    assert.equal(backend.reachable, true);
    assert.equal(backend.status, 200);
    assert.equal(backend.errorCode, null);
    assert.deepEqual(backend.release, {
      releaseId: expectedReleaseId,
      commitSha: expectedCommitSha,
      imageDigest: expectedImageDigest,
    });
    assert.doesNotMatch(
      JSON.stringify(backend),
      /worker-delegation-secret|windops-backend\.example/,
    );
    assert.equal(observedUrl, "https://windops-backend.example/api/v1/readyz");
    assert.equal(observedAuthorization, "");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("readiness and request proxy fail closed on missing or mismatched backend releases", async () => {
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = async () =>
      backendJson({
        status: "ready",
        release: {
          release_id: expectedReleaseId,
          commit_sha: expectedCommitSha,
          image_digest: `sha256:${"c".repeat(64)}`,
        },
      });
    const mismatch = await runWithWorkerEnv(productionEnvironment, () => probeProductionBackend());
    assert.equal(mismatch.reachable, false);
    assert.equal(mismatch.errorCode, "BACKEND_RELEASE_MISMATCH");
    assert.equal(mismatch.release.imageDigest, `sha256:${"c".repeat(64)}`);

    globalThis.fetch = async () => Response.json({ data: [] });
    const missing = await runWithWorkerEnv(productionEnvironment, () =>
      proxyProductionBackendRequest(
        sitesRequest("https://windops.example/api/backend/turbines"),
        "/api/v1/turbines",
      ),
    );
    assert.equal(missing.status, 503);
    assert.equal((await missing.json()).error.code, "BACKEND_RELEASE_IDENTITY_MISSING");

    globalThis.fetch = async () =>
      Response.json(
        { data: [] },
        {
          headers: {
            "x-windops-release-id": expectedReleaseId,
            "x-windops-commit-sha": expectedCommitSha,
            "x-windops-image-digest": `sha256:${"c".repeat(64)}`,
          },
        },
      );
    const wrongImage = await runWithWorkerEnv(productionEnvironment, () =>
      proxyProductionBackendRequest(
        sitesRequest("https://windops.example/api/backend/turbines"),
        "/api/v1/turbines",
      ),
    );
    assert.equal(wrongImage.status, 503);
    assert.equal((await wrongImage.json()).error.code, "BACKEND_RELEASE_MISMATCH");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("the backend gateway is allowlisted, server-authenticated, bounded, and identity-aware", async () => {
  assert.equal(isAllowedProductionGatewayPath("/api/v1/platform/configuration-status"), true);
  assert.equal(
    isAllowedProductionGatewayPath(
      "/api/v1/platform/configuration-security-audits/audit-42/rotation-confirmation",
    ),
    true,
  );
  const originalFetch = globalThis.fetch;
  let upstreamRequest = null;
  globalThis.fetch = async (input, init) => {
    upstreamRequest = { url: String(input), init };
    return backendJson(
      { data: [{ observedAt: "2026-08-14T00:00:00Z", value: 4.2 }] },
      { headers: { etag: '"scada-v1"', "set-cookie": "must-not-be-forwarded=1" } },
    );
  };
  try {
    const response = await runWithWorkerEnv(productionEnvironment, () =>
      proxyProductionBackendRequest(
        sitesRequest("https://windops.example/api/backend/turbines/WT-023/scada?limit=10", {
          headers: {
            accept: "application/json",
            "oai-authenticated-user-id": "user-42",
            "oai-authenticated-user-email": "operator@example.com",
            authorization: "Bearer browser-token-must-not-be-forwarded",
          },
        }),
        "/api/v1/turbines/WT-023/scada",
      ),
    );
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("x-windops-backend"), "python-fastapi");
    assert.equal(response.headers.get("x-windops-release-id"), expectedReleaseId);
    assert.equal(response.headers.get("x-windops-commit-sha"), expectedCommitSha);
    assert.equal(response.headers.get("x-windops-image-digest"), expectedImageDigest);
    assert.equal(response.headers.get("etag"), '"scada-v1"');
    assert.equal(response.headers.get("set-cookie"), null);
    assert.equal(
      upstreamRequest.url,
      "https://windops-backend.example/api/v1/turbines/WT-023/scada?limit=10",
    );
    const headers = new Headers(upstreamRequest.init.headers);
    const delegatedToken = headers.get("authorization")?.replace(/^Bearer /, "") ?? "";
    const [delegatedHeader, delegatedBody, delegatedSignature] = delegatedToken.split(".");
    assert.equal(
      delegatedSignature,
      createHmac("sha256", delegationSecret)
        .update(`${delegatedHeader}.${delegatedBody}`)
        .digest("base64url"),
    );
    const delegatedPayload = JSON.parse(
      Buffer.from(delegatedBody ?? "", "base64url").toString("utf8"),
    );
    assert.equal(delegatedPayload.sub, "sites-user-42");
    assert.equal(delegatedPayload.method, "GET");
    assert.equal(delegatedPayload.target, "/api/v1/turbines/WT-023/scada?limit=10");
    assert.equal(
      delegatedPayload.body_sha256,
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    );
    assert.equal(headers.get("x-windops-user-id"), "sites-user-42");
    assert.equal(headers.get("x-windops-user-email"), "operator@example.com");

    const unauthenticated = await runWithWorkerEnv(productionEnvironment, () =>
      proxyProductionBackendRequest(
        new Request("https://windops.example/api/backend/turbines"),
        "/api/v1/turbines",
      ),
    );
    assert.equal(unauthenticated.status, 401);
    assert.equal((await unauthenticated.json()).error.code, "UNAUTHENTICATED");

    const disallowed = await runWithWorkerEnv(productionEnvironment, () =>
      proxyProductionBackendRequest(
        sitesRequest("https://windops.example/api/backend/admin/secrets"),
        "/api/v1/admin/secrets",
      ),
    );
    assert.equal(disallowed.status, 404);
    assert.equal((await disallowed.json()).error.code, "BACKEND_PATH_NOT_ALLOWED");

    const tooLarge = await runWithWorkerEnv(productionEnvironment, () =>
      proxyProductionBackendRequest(
        sitesRequest("https://windops.example/api/backend/scada/ingest", {
          method: "POST",
          headers: { "content-type": "application/json", "content-length": "2097153" },
          body: "{}",
        }),
        "/api/v1/scada/ingest",
      ),
    );
    assert.equal(tooLarge.status, 413);
    assert.equal((await tooLarge.json()).error.code, "BACKEND_REQUEST_TOO_LARGE");

    const stream = await runWithWorkerEnv(productionEnvironment, () =>
      proxyProductionBackendRequest(
        sitesRequest("https://windops.example/api/agent-events?event_type=alarm.opened", {
          headers: { "last-event-id": "41" },
        }),
        "/api/v1/events/stream",
      ),
    );
    assert.equal(stream.status, 200);
    assert.equal(
      upstreamRequest.url,
      "https://windops-backend.example/api/v1/events/stream?event_type=alarm.opened",
    );
    assert.equal(new Headers(upstreamRequest.init.headers).get("last-event-id"), "41");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("production alarm commands are transformed and delegated to the authoritative backend", async () => {
  const originalFetch = globalThis.fetch;
  let observedUrl = "";
  let observedInit;
  globalThis.fetch = async (input, init) => {
    observedUrl = String(input);
    observedInit = init;
    return backendJson(
      {
        alarm_id: "ALARM-PROD",
        action: "unassign",
        status: "acknowledged",
        assigned_to: null,
        revision: 5,
        replayed: false,
      },
      { headers: { "idempotency-replayed": "true" } },
    );
  };
  try {
    const response = await fetchWorker("/api/alarms", productionEnvironment, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "oai-authenticated-user-id": "sites-user-42",
        "oai-authenticated-user-email": "operator@example.com",
      },
      body: JSON.stringify({
        alarmId: "ALARM-PROD",
        action: "assign",
        assignee: null,
        correlationId: "alarm-command-correlation-42",
        idempotencyKey: "alarm-command-idempotency-42",
        expectedRevision: 4,
        reason: "Operator released the assignment",
      }),
    });
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("idempotency-replayed"), "true");
    assert.equal(observedUrl, "https://windops-backend.example/api/v1/alarms/ALARM-PROD");
    const headers = new Headers(observedInit.headers);
    assert.equal(headers.get("idempotency-key"), "alarm-command-idempotency-42");
    assert.equal(headers.get("x-correlation-id"), "alarm-command-correlation-42");
    const delegated = JSON.parse(new TextDecoder().decode(observedInit.body));
    assert.deepEqual(delegated, {
      action: "unassign",
      expected_revision: 4,
      reason: "Operator released the assignment",
    });
    const token = headers.get("authorization").slice("Bearer ".length);
    const payload = JSON.parse(Buffer.from(token.split(".")[1], "base64url").toString("utf8"));
    assert.equal(payload.method, "POST");
    assert.equal(payload.target, "/api/v1/alarms/ALARM-PROD");

    const invalid = await fetchWorker("/api/alarms", productionEnvironment, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "oai-authenticated-user-id": "sites-user-42",
      },
      body: JSON.stringify({
        alarmId: "ALARM-PROD",
        action: "acknowledge",
        correlationId: "alarm-invalid",
        idempotencyKey: "alarm-invalid-idempotency",
      }),
    });
    assert.equal(invalid.status, 400);
    assert.equal((await invalid.json()).error.code, "INVALID_ALARM_COMMAND");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("production SCADA history rejects a missing turbineId without contacting the backend", async () => {
  const originalFetch = globalThis.fetch;
  let backendCalled = false;
  globalThis.fetch = async () => {
    backendCalled = true;
    return backendJson({});
  };
  try {
    const response = await runWithWorkerEnv(productionEnvironment, () =>
      productionScadaHistoryResponse(sitesRequest("https://windops.example/api/scada-history")),
    );
    assert.equal(response.status, 422);
    assert.equal((await response.json()).error.code, "TURBINE_ID_REQUIRED");
    assert.equal(backendCalled, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("production domain adapters expose authoritative mission, alarm, and work-order data", async () => {
  const originalFetch = globalThis.fetch;
  const observedUrls = [];
  globalThis.fetch = async (input) => {
    const url = String(input);
    observedUrls.push(url);
    if (url.includes("/api/v1/scada/history")) {
      return backendJson({
        data: [
          {
            series_id: "offshore-opcua-01:WT-900:main_bearing_vibration_rms",
            source_id: "offshore-opcua-01",
            turbine_id: "WT-900",
            variable: "main_bearing_vibration_rms",
            label: "Main bearing vibration RMS",
            unit: "mm/s",
            precision: 2,
            normal_range: [0, 4.5],
            thresholds: [
              {
                id: "WT-900-main-bearing-vibration-warning",
                label: "Warning threshold",
                value: 4.5,
                direction: "above",
                severity: "warning",
              },
            ],
            points: [
              {
                timestamp: "2026-08-14T00:00:00Z",
                value: 3.2,
                quality: "good",
                late: false,
                is_anomaly: false,
              },
            ],
          },
        ],
        meta: {
          point_count: 1,
          turbine_id: "WT-900",
          range: "CUSTOM",
          interval_seconds: 60,
          starts_at: "2026-08-14T00:00:00Z",
          ends_at: "2026-08-14T01:00:00Z",
          snapshot_at: "2026-08-14T01:00:01Z",
          deterministic: false,
        },
      });
    }
    if (url.includes("/api/v1/scada/measurements")) {
      return backendJson({
        measurements: [
          {
            sample_id: "SAMPLE-1",
            source_event_id: "OPC-1",
            source_id: "offshore-opcua-01",
            source_sequence: 81,
            turbine_id: "WT-900",
            variable: "main_bearing_vibration_rms",
            label: "Main bearing vibration RMS",
            observed_at: "2026-08-14T00:00:00Z",
            received_at: "2026-08-14T00:00:01Z",
            value: 3.2,
            unit: "mm/s",
            quality: "good",
            quality_code: "OPC_GOOD",
            late: false,
            is_anomaly: false,
          },
        ],
        meta: {
          total: 1,
          offset: 0,
          limit: 100,
          turbine_id: "WT-900",
          variable: "main_bearing_vibration_rms",
          snapshot_at: "2026-08-14T01:00:01Z",
        },
      });
    }
    if (url.includes("/api/v1/health/assessments")) {
      return backendJson({
        assessments: [
          {
            assessment_id: "HEALTH-WT-900",
            turbine_id: "WT-900",
            turbine_model: "GW200",
            health_score: 94,
            state: "healthy",
            trend: "stable",
            risk_level: "low",
            active_alarm_count: 0,
            failure_probability_30d: null,
            remaining_useful_life_days: null,
            anomaly_score: null,
            prediction_available: false,
            primary_finding: "No active condition finding is recorded",
            mission_id: null,
            assessed_at: "2026-08-14T01:00:00Z",
          },
        ],
        meta: {
          count: 1,
          total: 1,
          snapshot_at: "2026-08-14T01:00:01Z",
          prediction_provider: null,
        },
      });
    }
    if (url.includes("/api/v1/turbines")) {
      return backendJson({
        count: 1,
        turbines: [
          {
            turbine_id: "WT-900",
            wind_farm_id: "WF-PROD",
            model: "GW200",
            status: "running",
            health_score: 94,
            updated_at: "2026-08-14T01:00:00Z",
          },
        ],
      });
    }
    if (url.includes("/api/v1/decisions")) {
      return backendJson({
        count: 1,
        decisions: [
          {
            decision_id: "DEC-PROD",
            mission_id: "MISSION-20260814-PROD",
            mission_revision: 3,
            turbine_id: "WT-900",
            incident: "Gearbox condition investigation",
            diagnosis: { conclusion: "Gearbox cooling degradation", confidence: 0.91 },
            evidence_ids: ["EVD-1"],
            status: "pending_approval",
            alternatives: [
              {
                alternative_id: "ALT-B",
                title: "Derate and inspect",
                action: "Derate to 70% and inspect in the safe window.",
                safety_risk: "medium",
                estimated_downtime_hours: 10,
                estimated_cost_cny: 260000,
                estimated_energy_loss_mwh: 14,
                deterioration_risk_percent: 12,
                weather_window_id: "WX-1",
                required_resources: ["crew", "vessel"],
                recommended: true,
                rationale: "Balanced governed intervention.",
              },
            ],
            recommended_alternative_id: "ALT-B",
            selected_alternative_id: null,
            recommendation_reason: "Balanced governed intervention.",
            risks: [],
            approval: null,
            created_at: "2026-08-14T01:00:00Z",
            updated_at: "2026-08-14T01:05:00Z",
          },
        ],
      });
    }
    if (url.includes("/api/v1/missions")) {
      return backendJson({
        count: 1,
        missions: [
          {
            mission_id: "MISSION-20260814-PROD",
            alarm_id: "ALARM-PROD",
            turbine_id: "WT-900",
            title: "Gearbox condition investigation",
            status: "under_review",
            severity: "major",
            diagnosis: { conclusion: "Gearbox cooling degradation", confidence: 0.91 },
            evidence_ids: ["EVD-1"],
            decision_id: "DEC-1",
            work_order_id: null,
            created_at: "2026-08-14T01:00:00Z",
            updated_at: "2026-08-14T01:05:00Z",
          },
        ],
      });
    }
    if (url.includes("/api/v1/alarms")) {
      return backendJson({
        count: 1,
        alarms: [
          {
            alarm_id: "ALARM-PROD",
            turbine_id: "WT-900",
            code: "GB-TEMP-HIGH",
            subsystem: "gearbox",
            severity: "major",
            title: "Gearbox temperature high",
            status: "resolved",
            ai_status: "completed",
            triggered_at: "2026-08-14T00:00:00Z",
            acknowledged_at: "2026-08-14T00:05:00Z",
            acknowledged_by: "sites-user-42",
            assigned_to: "sites-user-42",
            resolved_at: "2026-08-15T08:00:00Z",
            revision: 4,
            updated_at: "2026-08-15T08:00:00Z",
            mission_id: "MISSION-20260814-PROD",
            evidence: { value: 91.2, unit: "degC", attributes: { threshold: 85 } },
          },
        ],
      });
    }
    if (url.includes("/api/v1/resources")) {
      return backendJson({
        count: 2,
        resources: [
          {
            resource_id: "CREW-A",
            resource_type: "crew",
            name: "Offshore Team A",
            quantity: 1,
            status: "reserved",
            attributes: {
              specialties: ["gearbox"],
              member_count: 6,
              certifications: ["LOTO"],
              current_location: "O&M Base",
            },
            reservations: [{ work_order_id: "WO-20260814-PROD", quantity: 1 }],
            updated_at: "2026-08-14T02:00:00Z",
          },
          {
            resource_id: "SPARE-A",
            resource_type: "spare_part",
            name: "Gearbox Cooling Kit",
            quantity: 2,
            status: "available",
            attributes: {
              part_number: "GB-COOL-01",
              category: "gearbox",
              warehouse: "Warehouse A",
              reorder_point: 1,
              unit: "kit",
              compatible_turbine_models: ["GW165"],
            },
            reservations: [],
            updated_at: "2026-08-14T02:00:00Z",
          },
        ],
        weather_windows: [
          {
            window_id: "WX-1",
            wind_farm_id: "WF-1",
            starts_at: "2026-08-15T01:00:00Z",
            ends_at: "2026-08-15T09:00:00Z",
            wind_speed_ms: 8,
            wave_height_m: 1.2,
            suitable: true,
            attributes: {
              gust_speed_mps: 10,
              visibility_km: 20,
              precipitation_mm: 0,
              lightning_risk: "none",
              temperature_c: 24,
              reason: "Within limits",
              recommended_for: ["inspection"],
            },
          },
        ],
      });
    }
    return backendJson({
      count: 1,
      work_orders: [
        {
          work_order_id: "WO-20260814-PROD",
          mission_id: "MISSION-20260814-PROD",
          turbine_id: "WT-900",
          title: "WT-900 Gearbox Inspection",
          status: "completed",
          priority: "high",
          assigned_team: "Offshore Team B",
          created_by: "work_order_agent",
          safety_plan: { risk_level: "high", procedures: ["LOTO"] },
          closure_policy: { component: "gearbox" },
          tasks: [{ task_id: "TASK-1", sequence: 1, title: "Inspect", status: "completed" }],
          planned_start: "2026-08-15T01:00:00Z",
          deadline: "2026-08-15T09:00:00Z",
          estimated_duration_hours: 8,
          created_at: "2026-08-14T02:00:00Z",
          updated_at: "2026-08-15T08:00:00Z",
          eam: {
            provider: "eam",
            external_id: "EAM-WO-9001",
            sync_status: "in_progress",
            external_updated_at: "2026-08-15T08:05:00Z",
            updated_at: "2026-08-15T08:05:01Z",
          },
        },
      ],
    });
  };
  try {
    const missionResponse = await runWithWorkerEnv(productionEnvironment, () =>
      productionMissionsResponse(sitesRequest("https://windops.example/api/missions")),
    );
    assert.equal(missionResponse.status, 200);
    const mission = (await missionResponse.json()).data[0];
    assert.equal(mission.status, "under-review");
    assert.equal(mission.diagnosis, "Gearbox cooling degradation");
    assert.equal(mission.confidencePercent, 91);

    const decisionResponse = await runWithWorkerEnv(productionEnvironment, () =>
      productionDecisionsResponse(sitesRequest("https://windops.example/api/decisions")),
    );
    const decision = (await decisionResponse.json()).data[0];
    assert.equal(decision.status, "under-review");
    assert.equal(decision.missionRevision, 3);
    assert.equal(decision.alternatives[0].estimatedEnergyLossMWh, 14);

    const alarmResponse = await runWithWorkerEnv(productionEnvironment, () =>
      productionAlarmsResponse(sitesRequest("https://windops.example/api/alarms?scope=archive")),
    );
    const alarm = (await alarmResponse.json()).data[0];
    assert.equal(alarm.currentValue, 91.2);
    assert.equal(alarm.assignee, "sites-user-42");
    assert.equal(alarm.acknowledgedAt, "2026-08-14T00:05:00Z");
    assert.equal(alarm.resolvedAt, "2026-08-15T08:00:00Z");
    assert.equal(alarm.revision, 4);

    const workOrderResponse = await runWithWorkerEnv(productionEnvironment, () =>
      productionWorkOrdersResponse(
        sitesRequest("https://windops.example/api/work-orders?scope=archive"),
      ),
    );
    const workOrder = (await workOrderResponse.json()).data[0];
    assert.equal(workOrder.tasks[0].completed, true);
    assert.equal(workOrder.plannedStart, "2026-08-15T01:00:00Z");
    assert.equal(workOrder.eam.externalId, "EAM-WO-9001");
    assert.equal(workOrder.eam.syncStatus, "in_progress");

    const resourceResponse = await runWithWorkerEnv(productionEnvironment, () =>
      productionResourcesResponse(sitesRequest("https://windops.example/api/resources")),
    );
    const resourceBody = await resourceResponse.json();
    assert.equal(resourceBody.meta.deterministic, false);
    assert.equal(resourceBody.data.crews[0].assignedWorkOrderId, "WO-20260814-PROD");
    assert.equal(resourceBody.data.spareParts[0].partNumber, "GB-COOL-01");
    assert.equal(resourceBody.data.weatherWindows[0].visibilityKm, 20);

    const turbineResponse = await runWithWorkerEnv(productionEnvironment, () =>
      productionTurbinesResponse(sitesRequest("https://windops.example/api/turbines")),
    );
    assert.equal((await turbineResponse.json()).data[0].model, "GW200");

    const scadaResponse = await runWithWorkerEnv(productionEnvironment, () =>
      productionScadaHistoryResponse(
        sitesRequest(
          "https://windops.example/api/scada-history?turbineId=WT-900&from=2026-08-14T00%3A00%3A00%2B08%3A00&to=2026-08-14T01%3A00%3A00%2B08%3A00",
        ),
      ),
    );
    const scadaBody = await scadaResponse.json();
    assert.equal(scadaBody.meta.deterministic, false);
    assert.equal(scadaBody.data[0].sourceId, "offshore-opcua-01");
    assert.equal(scadaBody.data[0].metric, "main-bearing-vibration-rms");

    const archiveResponse = await runWithWorkerEnv(productionEnvironment, () =>
      productionScadaMeasurementsResponse(
        sitesRequest(
          "https://windops.example/api/scada-measurements?turbineId=WT-900&metric=main-bearing-vibration-rms",
        ),
      ),
    );
    const archiveBody = await archiveResponse.json();
    assert.equal(archiveBody.meta.deterministic, false);
    assert.equal(archiveBody.data[0].qualityCode, "OPC_GOOD");

    const healthResponse = await runWithWorkerEnv(productionEnvironment, () =>
      productionHealthAssessmentsResponse(
        sitesRequest("https://windops.example/api/health-assessments?turbineId=WT-900"),
      ),
    );
    const healthBody = await healthResponse.json();
    assert.equal(healthBody.meta.deterministic, false);
    assert.equal(healthBody.data[0].predictionAvailable, false);
    assert.equal(healthBody.data[0].turbineModel, "GW200");

    assert.ok(observedUrls.some((url) => url.endsWith("/api/v1/missions")));
    assert.ok(observedUrls.some((url) => url.endsWith("/api/v1/decisions")));
    assert.ok(observedUrls.some((url) => url.endsWith("/api/v1/alarms?status=resolved")));
    assert.ok(observedUrls.some((url) => url.endsWith("/api/v1/work-orders?status=completed")));
    assert.ok(observedUrls.some((url) => url.endsWith("/api/v1/resources")));
    assert.ok(observedUrls.some((url) => url.includes("/api/v1/scada/history?turbine_id=WT-900")));
    assert.ok(observedUrls.some((url) => url.endsWith("/api/v1/turbines?limit=200")));
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("production collection adapters preserve one backend page and its cursor", async () => {
  const originalFetch = globalThis.fetch;
  const observedUrls = [];
  globalThis.fetch = async (input) => {
    const url = String(input);
    observedUrls.push(url);
    if (!url.includes("/api/v1/work-orders")) {
      return backendJson({ work_orders: [] });
    }
    return backendJson({
      work_orders: [
        {
          work_order_id: "WO-1",
          turbine_id: "WT-1",
          title: "First page",
          status: "completed",
          created_at: "2026-08-14T00:00:00Z",
        },
      ],
      total: 2,
      next_cursor: "cursor-1",
    });
  };
  try {
    const response = await runWithWorkerEnv(productionEnvironment, () =>
      productionWorkOrdersResponse(sitesRequest("https://windops.example/api/work-orders")),
    );
    assert.equal(response.status, 200);
    const body = await response.json();
    assert.deepEqual(
      body.data.map((row) => row.id),
      ["WO-1"],
    );
    assert.equal(body.meta.count, 1);
    assert.equal(body.meta.total, 2);
    assert.equal(body.meta.nextCursor, "cursor-1");
    assert.equal(body.meta.hasMore, true);
    assert.equal(observedUrls.length, 1);
    assert.ok(!observedUrls[0].includes("cursor=cursor-1"));
  } finally {
    globalThis.fetch = originalFetch;
  }
});
