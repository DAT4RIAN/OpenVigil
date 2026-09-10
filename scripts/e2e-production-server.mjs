import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";

const PORT = Number(process.env.WINDOPS_E2E_PORT ?? "4179");
const ORIGIN = `http://127.0.0.1:${PORT}`;
const REAL_BACKEND = process.env.WINDOPS_E2E_REAL_BACKEND === "1";
const BACKEND_ORIGIN =
  process.env.WINDOPS_E2E_BACKEND_ORIGIN ?? "https://windops-e2e-backend.invalid";
const RELEASE_ID = process.env.WINDOPS_E2E_RELEASE_ID ?? "windops-e2e-2026.08.19";
const COMMIT_SHA = process.env.WINDOPS_E2E_COMMIT_SHA ?? "a".repeat(40);
const IMAGE_DIGEST = process.env.WINDOPS_E2E_IMAGE_DIGEST ?? `sha256:${"b".repeat(64)}`;
const configuredDelegationSecret = process.env.WINDOPS_GATEWAY_DELEGATION_SECRET?.trim();
if (REAL_BACKEND && !configuredDelegationSecret) {
  throw new Error("WINDOPS_GATEWAY_DELEGATION_SECRET is required when WINDOPS_E2E_REAL_BACKEND=1");
}
const DELEGATION_SECRET =
  configuredDelegationSecret ??
  "mock-only-e2e-delegation-secret-with-at-least-forty-eight-characters";
const CLIENT_ROOT = resolve("dist/client");
const nativeFetch = globalThis.fetch;

const calls = new Map();
const approvalCalls = [];
const recoveredSubjects = new Set();

const viewCapabilities = [
  "view.alarms",
  "view.assets",
  "view.dashboard",
  "view.decisions",
  "view.knowledge",
  "view.missions",
  "view.platform",
  "view.resources",
  "view.telemetry",
  "view.work_orders",
];

const roleCapabilities = {
  "user-manager": [
    ...viewCapabilities,
    "view.agents",
    "view.models",
    "view.reports",
    "agent.manage",
    "alarm.command",
    "mission.comment",
    "mission.create",
    "mission.escalate",
    "model.manage",
    "platform.manage",
    "report.generate",
    "resource.manage",
    "work_order.schedule",
  ],
  "user-approver": [
    ...viewCapabilities,
    "alarm.command",
    "mission.approve",
    "mission.comment",
    "mission.reject",
  ],
  "user-reviewer": [...viewCapabilities, "mission.request_revision"],
  "user-field": [...viewCapabilities, "mission.comment", "work_order.task.complete"],
};

function countCall(method, pathname) {
  const key = `${method} ${pathname}`;
  calls.set(key, (calls.get(key) ?? 0) + 1);
}

function releaseHeaders(headers = {}) {
  return {
    "x-windops-release-id": RELEASE_ID,
    "x-windops-commit-sha": COMMIT_SHA,
    "x-windops-image-digest": IMAGE_DIGEST,
    ...headers,
  };
}

function backendJson(body, init = {}) {
  return Response.json(body, {
    ...init,
    headers: releaseHeaders(init.headers),
  });
}

function delegatedSubject(init) {
  try {
    const token = new Headers(init?.headers).get("authorization")?.replace(/^Bearer /, "") ?? "";
    const payload = token.split(".")[1];
    return JSON.parse(Buffer.from(payload, "base64url").toString("utf8")).sub ?? null;
  } catch {
    return null;
  }
}

function roleForSubject(subject) {
  if (subject === "user-field") return "field_technician";
  if (subject === "user-approver") return "operations_approver";
  if (subject === "user-reviewer") return "maintenance_reviewer";
  return "operations_manager";
}

function sessionForSubject(subject) {
  const capabilitySubject = subject?.startsWith("user-error-") ? "user-manager" : subject;
  return {
    subject,
    email: `${subject}@example.com`,
    roles: [roleForSubject(capabilitySubject)],
    capabilities: roleCapabilities[capabilitySubject] ?? [],
    scope: {
      tenant_count: 1,
      wind_farm_count: 1,
      turbine_count: 1,
      entity_count: 0,
      allow_global: capabilitySubject === "user-manager",
    },
  };
}

const missionDetail = {
  mission_id: "MISSION-E2E-001",
  alarm_id: "ALARM-E2E-001",
  turbine_id: "WT-E2E-001",
  title: "E2E bearing review",
  status: "under_review",
  revision: 7,
  public_state: { diagnosis: { conclusion: "bearing vibration requires review" } },
  work_order_id: null,
  evidence: [],
  decision: {
    decision_id: "DECISION-E2E-001",
    status: "pending_approval",
    recommendation_reason: "Controlled E2E recommendation",
    recommended_alternative_id: "ALT-E2E-001",
    selected_alternative_id: null,
    alternatives: [{ alternative_id: "ALT-E2E-001", title: "Inspect bearing" }],
  },
  approvals: [],
  executions: [],
  created_at: "2026-08-19T00:00:00Z",
  updated_at: "2026-08-19T00:10:00Z",
};

function backendEventStream() {
  const event = {
    sequence: 42,
    event_id: "EVENT-E2E-042",
    event_type: "alarm.opened",
    aggregate_type: "alarm",
    aggregate_id: "ALARM-E2E-001",
    payload: { severity: "major" },
    occurred_at: "2026-08-19T00:12:00Z",
  };
  const body = [
    "event: stream.ready",
    "id: 41",
    'data: {"next_cursor":41}',
    "",
    "event: alarm.opened",
    "id: 42",
    `data: ${JSON.stringify(event)}`,
    "",
    "event: reconnect",
    "id: 42",
    'data: {"next_cursor":42}',
    "",
    "",
  ].join("\n");
  return new Response(body, {
    headers: releaseHeaders({
      "cache-control": "no-cache, no-transform",
      "content-type": "text/event-stream; charset=utf-8",
      "x-accel-buffering": "no",
    }),
  });
}

async function mockBackendFetch(input, init) {
  const url = new URL(String(input));
  const method = (init?.method ?? "GET").toUpperCase();
  countCall(method, url.pathname);

  if (url.pathname === "/api/v1/readyz") {
    return backendJson({
      status: "ready",
      release: {
        release_id: RELEASE_ID,
        commit_sha: COMMIT_SHA,
        image_digest: IMAGE_DIGEST,
      },
    });
  }

  const subject = delegatedSubject(init);
  if (url.pathname === "/api/v1/session") {
    if (subject === "machine-scada" || subject === "machine-eam") {
      return backendJson(
        {
          error: {
            code: "BUSINESS_READ_FORBIDDEN",
            message: "Machine identities cannot use the shell",
          },
        },
        { status: 403 },
      );
    }
    if (!subject) {
      return backendJson(
        { error: { code: "UNAUTHENTICATED", message: "A delegated subject is required" } },
        { status: 401 },
      );
    }
    return backendJson(sessionForSubject(subject));
  }

  const forcedStatus = {
    "user-error-401": 401,
    "user-error-403": 403,
    "user-error-503": 503,
  }[subject];
  if (
    forcedStatus &&
    url.pathname.startsWith("/api/v1/platform/") &&
    !recoveredSubjects.has(subject)
  ) {
    return backendJson(
      {
        error: {
          code: `E2E_${forcedStatus}`,
          message: `E2E forced platform failure ${forcedStatus}`,
        },
      },
      { status: forcedStatus },
    );
  }

  if (url.pathname === "/api/v1/platform/configurations") {
    return backendJson({
      configurations: [],
      meta: {
        secrets_redacted: true,
        serialization_verified: true,
        snapshot_at: "2026-08-19T00:00:00Z",
      },
    });
  }
  if (url.pathname === "/api/v1/platform/configuration-status") {
    return backendJson({
      data: {
        status: "ready",
        configured_keys: [],
        configuration_count: 0,
        pending_credential_rotations: 0,
      },
      meta: { redacted: true, snapshot_at: "2026-08-19T00:00:00Z" },
    });
  }
  if (url.pathname === "/api/v1/missions/MISSION-E2E-001" && method === "GET") {
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 100));
    return backendJson(missionDetail);
  }
  if (url.pathname === "/api/v1/missions/MISSION-E2E-001/comments" && method === "GET") {
    return backendJson({ comments: [] });
  }
  if (url.pathname === "/api/v1/missions/MISSION-E2E-001/approvals" && method === "POST") {
    const body = JSON.parse(Buffer.from(init.body).toString("utf8"));
    approvalCalls.push({
      subject,
      body,
      idempotencyKey: new Headers(init.headers).get("idempotency-key"),
    });
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 100));
    return backendJson({ mission_status: "approved", work_order_id: "WO-E2E-001" });
  }
  if (url.pathname === "/api/v1/alarms") {
    return backendJson({
      alarms: [
        {
          alarm_id: "ALARM-E2E-001",
          code: "MB-VIB-E2E",
          turbine_id: "WT-E2E-001",
          subsystem: "main-bearing",
          severity: "major",
          title: "E2E bearing alarm",
          triggered_at: "2026-08-19T00:00:00Z",
          status: "open",
          ai_status: "review_ready",
          assigned_to: null,
          acknowledged_at: null,
          resolved_at: null,
          mission_id: "MISSION-E2E-001",
          evidence: {
            variable: "vibration_rms",
            value: 8.2,
            unit: "mm/s",
            attributes: { threshold: 6.3 },
          },
          revision: 1,
          updated_at: "2026-08-19T00:10:00Z",
        },
      ],
      next_cursor: null,
      meta: { total: 1 },
    });
  }
  if (url.pathname === "/api/v1/alarms/ALARM-E2E-001") {
    return backendJson({
      alarm_id: "ALARM-E2E-001",
      mission_id: "MISSION-E2E-001",
      evidence: {
        variable: "vibration_rms",
        value: 8.2,
        unit: "mm/s",
        attributes: { threshold: 6.3 },
      },
    });
  }
  if (url.pathname === "/api/v1/knowledge/cases") {
    return backendJson({ count: 0, cases: [] });
  }
  if (url.pathname === "/api/v1/knowledge/documents") {
    return backendJson({ count: 0, documents: [] });
  }
  if (url.pathname === "/api/v1/events/stream") return backendEventStream();
  if (url.pathname === "/api/v1/work-orders") {
    return backendJson({ work_orders: [], next_cursor: null, meta: { total: 0 } });
  }
  if (url.pathname === "/api/v1/resources") {
    return backendJson({
      resources: [],
      reservations: [],
      weather_windows: [],
      meta: { total: 0, reservation_total: 0, weather_total: 0 },
    });
  }
  if (url.pathname === "/api/v1/models") {
    return backendJson({ models: [], deployments: [], meta: { total: 0 } });
  }
  return backendJson({ data: [], meta: { total: 0 } });
}

globalThis.fetch = async (input, init) => {
  if (!REAL_BACKEND && String(input).startsWith(BACKEND_ORIGIN)) {
    return mockBackendFetch(input, init);
  }
  return nativeFetch(input, init);
};

const workerUrl = new URL("../dist/server/index.js", import.meta.url);
workerUrl.searchParams.set("e2e", `${process.pid}-${Date.now()}`);
const { default: worker } = await import(workerUrl.href);

const mimeTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
};

const assetBinding = {
  async fetch(request) {
    let pathname;
    try {
      pathname = decodeURIComponent(new URL(request.url).pathname);
    } catch {
      return new Response("Invalid asset path", { status: 400 });
    }
    const target = resolve(CLIENT_ROOT, pathname.replace(/^\/+/, ""));
    if (target !== CLIENT_ROOT && !target.startsWith(`${CLIENT_ROOT}${sep}`)) {
      return new Response("Not found", { status: 404 });
    }
    try {
      const content = await readFile(target);
      return new Response(content, {
        headers: {
          "cache-control": "public, max-age=31536000, immutable",
          "content-type": mimeTypes[extname(target)] ?? "application/octet-stream",
        },
      });
    } catch {
      return new Response("Not found", { status: 404 });
    }
  },
};

const productionEnvironment = {
  ASSETS: assetBinding,
  WINDOPS_RUNTIME_MODE: "production",
  WINDOPS_BACKEND_BASE_URL: BACKEND_ORIGIN,
  WINDOPS_BACKEND_AUTH_MODE: "sites_delegation",
  WINDOPS_BACKEND_DELEGATION_SECRET: DELEGATION_SECRET,
  WINDOPS_BACKEND_REQUEST_TIMEOUT_MS: "5000",
  WINDOPS_BACKEND_EXPECTED_RELEASE_ID: RELEASE_ID,
  WINDOPS_BACKEND_EXPECTED_IMAGE_DIGEST: IMAGE_DIGEST,
};
const demoEnvironment = { ASSETS: assetBinding, WINDOPS_RUNTIME_MODE: "demo" };
const context = { waitUntil() {}, passThroughOnException() {} };

function nodeHeaders(headers) {
  const result = new Headers();
  for (const [name, value] of Object.entries(headers)) {
    if (value !== undefined) result.set(name, Array.isArray(value) ? value.join(", ") : value);
  }
  result.delete("x-e2e-runtime");
  return result;
}

async function nodeRequest(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const method = req.method ?? "GET";
  const body = method === "GET" || method === "HEAD" ? undefined : Buffer.concat(chunks);
  return new Request(`${ORIGIN}${req.url}`, {
    method,
    headers: nodeHeaders(req.headers),
    body,
    redirect: "manual",
  });
}

function sendNodeResponse(res, response) {
  res.statusCode = response.status;
  response.headers.forEach((value, name) => res.setHeader(name, value));
  return response.arrayBuffer().then((body) => res.end(Buffer.from(body)));
}

const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url ?? "/", ORIGIN);
    if (url.pathname === "/__e2e/state") {
      return sendNodeResponse(
        res,
        Response.json({ calls: Object.fromEntries(calls), approvalCalls }),
      );
    }
    if (url.pathname === "/__e2e/reset" && req.method === "POST") {
      calls.clear();
      approvalCalls.length = 0;
      recoveredSubjects.clear();
      return sendNodeResponse(res, Response.json({ ok: true }));
    }
    if (url.pathname === "/__e2e/recover" && req.method === "POST") {
      const subject = url.searchParams.get("subject");
      if (subject) recoveredSubjects.add(subject);
      return sendNodeResponse(res, Response.json({ ok: Boolean(subject) }));
    }
    if (
      url.pathname.startsWith("/_next/") ||
      url.pathname.startsWith("/_vinext/") ||
      /\.(?:css|gif|ico|jpe?g|js|json|png|svg|webp|woff2?)$/i.test(url.pathname)
    ) {
      return sendNodeResponse(
        res,
        await assetBinding.fetch(new Request(`${ORIGIN}${url.pathname}`)),
      );
    }
    if (url.pathname === "/signin-with-chatgpt" || url.pathname === "/signout-with-chatgpt") {
      return sendNodeResponse(
        res,
        new Response(
          `<!doctype html><title>Sites dispatcher</title><h1>Sites dispatcher ${url.pathname.includes("signout") ? "sign-out" : "sign-in"}</h1>`,
          { headers: { "content-type": "text/html; charset=utf-8" } },
        ),
      );
    }
    const environment =
      req.headers["x-e2e-runtime"] === "demo" ? demoEnvironment : productionEnvironment;
    const response = await worker.fetch(await nodeRequest(req), environment, context);
    return sendNodeResponse(res, response);
  } catch (error) {
    res.statusCode = 500;
    res.setHeader("content-type", "text/plain; charset=utf-8");
    res.end(error instanceof Error ? error.stack : String(error));
  }
});

server.listen(PORT, "127.0.0.1", () => {
  process.stdout.write(`WindOps E2E server listening at ${ORIGIN}\n`);
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
