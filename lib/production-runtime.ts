import { getWorkerEnv } from "./worker-env.ts";
import { asText } from "./utils.ts";

export const OPENVIGIL_RUNTIME_MODES = ["demo", "production"] as const;
export type OpenVigilRuntimeMode = (typeof OPENVIGIL_RUNTIME_MODES)[number];
export const OPENVIGIL_BACKEND_AUTH_MODES = ["sites_delegation", "service_token"] as const;
export type OpenVigilBackendAuthMode = (typeof OPENVIGIL_BACKEND_AUTH_MODES)[number];

const DEFAULT_BACKEND_TIMEOUT_MS = 8_000;
const MIN_BACKEND_TIMEOUT_MS = 1_000;
const MAX_BACKEND_TIMEOUT_MS = 30_000;
const MAX_GATEWAY_BODY_BYTES = 2 * 1024 * 1024;
export const PREDICTIVE_ASSESSMENT_RUN_TIMEOUT_MS = 30_000;

const pathTimeoutsMs = new Map<string, number>([
  ["/api/v1/events/stream", 30_000],
  ["/api/v1/predictive-assessments/run", PREDICTIVE_ASSESSMENT_RUN_TIMEOUT_MS],
]);

const allowedGatewayPaths = [
  /^\/api\/v1\/(?:healthz|readyz)$/,
  /^\/api\/v1\/session$/,
  /^\/api\/v1\/(?:tools|catalog)$/,
  /^\/api\/v1\/dashboard$/,
  /^\/api\/v1\/turbines(?:\/[^/]+(?:\/(?:scada|health|twin-profile(?:\/artifacts\/(?:presign|view))?))?)?$/,
  /^\/api\/v1\/alarms(?:\/[^/]+)?$/,
  /^\/api\/v1\/missions(?:\/batch|\/[^/]+(?:\/(?:approvals|comments))?)?$/,
  /^\/api\/v1\/decisions$/,
  /^\/api\/v1\/agent-executions$/,
  /^\/api\/v1\/observability\/agent-executions\/24h$/,
  /^\/api\/v1\/events(?:\/stream)?$/,
  /^\/api\/v1\/ingest\/sources$/,
  /^\/api\/v1\/health\/assessments$/,
  /^\/api\/v1\/work-orders(?:\/[^/]+(?:\/schedule|\/tasks\/[^/]+\/(?:complete|artifacts\/presign))?)?$/,
  /^\/api\/v1\/resources(?:\/reassignments|\/[^/]+\/stock-adjustments)?$/,
  /^\/api\/v1\/platform\/(?:configurations|configuration-status|data-sources|data-contracts)$/,
  /^\/api\/v1\/platform\/(?:configuration-security-audits|data-source-security-audits)\/[^/]+\/rotation-confirmation$/,
  /^\/api\/v1\/knowledge\/(?:documents(?:\/uploads\/presign|\/[^/]+)?|cases)$/,
  /^\/api\/v1\/models(?:\/uploads\/presign|\/deployments\/[^/]+\/activate|\/[^/]+(?:\/deployments|\/rollback)?)?$/,
  /^\/api\/v1\/models\/deployments\/[A-Za-z0-9][A-Za-z0-9._-]{2,63}\/anomaly-predictions\/run$/,
  /^\/api\/v1\/model-predictions\/[A-Za-z0-9][A-Za-z0-9._-]{2,63}\/alert-evaluation$/,
  /^\/api\/v1\/predictive-assessments(?:\/run)?$/,
  /^\/api\/v1\/agents(?:\/[^/]+\/(?:commands|releases))?$/,
  /^\/api\/v1\/agent-tools$/,
  /^\/api\/v1\/(?:diagnoses|maintenance-plans|digital-twin|reports(?:\/[^/]+)?|data-catalog)$/,
  /^\/api\/v1\/scada\/(?:history|ingest|measurements|sample-count)$/,
  /^\/api\/v1\/knowledge-graph(?:\/.*)?$/,
  /^\/api\/v1\/benchmarks\/(?:datasets(?:\/[^/]+\/events)?|evaluations(?:\/[^/]+\/(?:results|exports))?|diagnoses|replay-runs\/[^/]+\/curve)$/,
] as const;

const migratedProductionApiPrefixes = [
  "/api/backend/",
  "/api/knowledge-graph",
  "/api/alarms",
  "/api/missions",
  "/api/decisions",
  "/api/work-orders",
  "/api/resources",
  "/api/reports",
] as const;

const migratedProductionApiExactPaths = [
  "/api/runtime",
  "/api/agent-events",
  "/api/scada-history",
  "/api/scada-measurements",
  "/api/health-assessments",
  "/api/turbines",
  "/api/knowledge-documents",
  "/api/knowledge-assistant",
  "/api/model-registry",
  "/api/predictive-assessments",
  "/api/agents",
  "/api/agent-tools",
  "/api/diagnoses",
  "/api/maintenance-plans",
  "/api/digital-twin",
  "/api/data-catalog",
] as const;

export class ProductionRuntimeError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status = 503) {
    super(message);
    this.name = "ProductionRuntimeError";
    this.code = code;
    this.status = status;
  }
}

export interface ProductionBackendConfig {
  readonly mode: OpenVigilRuntimeMode;
  readonly authMode: OpenVigilBackendAuthMode;
  readonly baseUrl: string | null;
  readonly apiToken: string | null;
  readonly delegationSecret: string | null;
  readonly timeoutMs: number;
  readonly expectedReleaseId: string | null;
  readonly expectedCommitSha: string | null;
  readonly expectedImageDigest: string | null;
}

export interface ProductionBackendRelease {
  readonly releaseId: string;
  readonly commitSha: string;
  readonly imageDigest: string;
}

function processValue(name: string): string | undefined {
  if (typeof process === "undefined") return undefined;
  return process.env[name];
}

function configuredValue(name: keyof ReturnType<typeof getWorkerEnv>): string | undefined {
  const workerValue = getWorkerEnv()[name];
  return typeof workerValue === "string" ? workerValue : processValue(String(name));
}

function runtimeMode(value: string | undefined): OpenVigilRuntimeMode {
  const normalized = value?.trim().toLowerCase() || "demo";
  if (!OPENVIGIL_RUNTIME_MODES.includes(normalized as OpenVigilRuntimeMode)) {
    throw new ProductionRuntimeError(
      "INVALID_RUNTIME_MODE",
      `WINDOPS_RUNTIME_MODE must be one of ${OPENVIGIL_RUNTIME_MODES.join(", ")}.`,
      500,
    );
  }
  return normalized as OpenVigilRuntimeMode;
}

function backendAuthMode(
  value: string | undefined,
  runtime: OpenVigilRuntimeMode,
): OpenVigilBackendAuthMode {
  const normalized = value?.trim().toLowerCase() || "sites_delegation";
  if (!OPENVIGIL_BACKEND_AUTH_MODES.includes(normalized as OpenVigilBackendAuthMode)) {
    throw new ProductionRuntimeError(
      "INVALID_BACKEND_AUTH_MODE",
      `WINDOPS_BACKEND_AUTH_MODE must be one of ${OPENVIGIL_BACKEND_AUTH_MODES.join(", ")}.`,
      500,
    );
  }
  if (runtime === "production" && normalized !== "sites_delegation") {
    throw new ProductionRuntimeError(
      "INSECURE_BACKEND_AUTH_MODE",
      "Production mode requires per-user Sites delegation.",
      500,
    );
  }
  return normalized as OpenVigilBackendAuthMode;
}

function backendTimeout(value: string | undefined): number {
  if (!value) return DEFAULT_BACKEND_TIMEOUT_MS;
  if (!/^\d+$/.test(value)) {
    throw new ProductionRuntimeError(
      "INVALID_BACKEND_TIMEOUT",
      "WINDOPS_BACKEND_REQUEST_TIMEOUT_MS must be an integer number of milliseconds.",
      500,
    );
  }
  const parsed = Number(value);
  if (parsed < MIN_BACKEND_TIMEOUT_MS || parsed > MAX_BACKEND_TIMEOUT_MS) {
    throw new ProductionRuntimeError(
      "INVALID_BACKEND_TIMEOUT",
      `WINDOPS_BACKEND_REQUEST_TIMEOUT_MS must be between ${MIN_BACKEND_TIMEOUT_MS} and ${MAX_BACKEND_TIMEOUT_MS}.`,
      500,
    );
  }
  return parsed;
}

function normalizedBackendUrl(
  value: string | undefined,
  mode: OpenVigilRuntimeMode,
): string | null {
  const candidate = value?.trim();
  if (!candidate) return null;
  let url: URL;
  try {
    url = new URL(candidate);
  } catch {
    throw new ProductionRuntimeError(
      "INVALID_BACKEND_URL",
      "WINDOPS_BACKEND_BASE_URL must be an absolute HTTP(S) URL.",
      500,
    );
  }
  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  ) {
    throw new ProductionRuntimeError(
      "INVALID_BACKEND_URL",
      "WINDOPS_BACKEND_BASE_URL must not contain credentials, a query, or a fragment.",
      500,
    );
  }
  if (mode === "production" && url.protocol !== "https:") {
    throw new ProductionRuntimeError(
      "INSECURE_BACKEND_URL",
      "Production mode requires an HTTPS WINDOPS_BACKEND_BASE_URL.",
      500,
    );
  }
  return url.toString().replace(/\/$/, "");
}

function normalizedToken(
  value: string | undefined,
  mode: OpenVigilRuntimeMode,
  authMode: OpenVigilBackendAuthMode,
): string | null {
  const token = value?.trim() || null;
  if (
    mode === "production" &&
    authMode === "service_token" &&
    (!token || token.length < 32 || /replace|change-me|development|example/i.test(token))
  ) {
    throw new ProductionRuntimeError(
      "INVALID_BACKEND_TOKEN",
      "Production mode requires a non-example backend service token of at least 32 characters.",
      500,
    );
  }
  return token;
}

function normalizedDelegationSecret(
  value: string | undefined,
  mode: OpenVigilRuntimeMode,
  authMode: OpenVigilBackendAuthMode,
): string | null {
  const secret = value?.trim() || null;
  if (
    mode === "production" &&
    authMode === "sites_delegation" &&
    (!secret || secret.length < 48 || /replace|change-me|development|example/i.test(secret))
  ) {
    throw new ProductionRuntimeError(
      "INVALID_DELEGATION_SECRET",
      "Production mode requires a non-example gateway delegation secret of at least 48 characters.",
      500,
    );
  }
  return secret;
}

function normalizedExpectedReleaseId(
  value: string | undefined,
  mode: OpenVigilRuntimeMode,
): string | null {
  const releaseId = value?.trim() || null;
  if (
    mode === "production" &&
    (!releaseId ||
      !/^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$/.test(releaseId) ||
      /replace|change-me|development|unknown|unreleased|example/i.test(releaseId))
  ) {
    throw new ProductionRuntimeError(
      "INVALID_EXPECTED_RELEASE_ID",
      "Production mode requires the immutable backend release ID.",
      500,
    );
  }
  return releaseId;
}

function normalizedExpectedImageDigest(
  value: string | undefined,
  mode: OpenVigilRuntimeMode,
): string | null {
  const digest = value?.trim() || null;
  if (
    mode === "production" &&
    (!digest || !/^sha256:[0-9a-f]{64}$/.test(digest) || digest === `sha256:${"0".repeat(64)}`)
  ) {
    throw new ProductionRuntimeError(
      "INVALID_EXPECTED_IMAGE_DIGEST",
      "Production mode requires the approved non-placeholder backend image digest.",
      500,
    );
  }
  return digest;
}

function normalizedExpectedCommitSha(
  value: string | undefined,
  mode: OpenVigilRuntimeMode,
): string | null {
  const commitSha = value?.trim() || null;
  if (
    mode === "production" &&
    (!commitSha ||
      !/^(?:[0-9a-f]{40}|[0-9a-f]{64})$/.test(commitSha) ||
      /^(?:0{40}|0{64})$/.test(commitSha))
  ) {
    throw new ProductionRuntimeError(
      "INVALID_EXPECTED_COMMIT_SHA",
      "Production mode requires the approved full backend commit SHA.",
      500,
    );
  }
  return commitSha;
}

export function getProductionBackendConfig(): ProductionBackendConfig {
  const mode = runtimeMode(configuredValue("WINDOPS_RUNTIME_MODE"));
  const authMode = backendAuthMode(configuredValue("WINDOPS_BACKEND_AUTH_MODE"), mode);
  const baseUrl = normalizedBackendUrl(configuredValue("WINDOPS_BACKEND_BASE_URL"), mode);
  const apiToken = normalizedToken(configuredValue("WINDOPS_BACKEND_API_TOKEN"), mode, authMode);
  const delegationSecret = normalizedDelegationSecret(
    configuredValue("WINDOPS_BACKEND_DELEGATION_SECRET"),
    mode,
    authMode,
  );
  const timeoutMs = backendTimeout(configuredValue("WINDOPS_BACKEND_REQUEST_TIMEOUT_MS"));
  const expectedReleaseId = normalizedExpectedReleaseId(
    configuredValue("WINDOPS_BACKEND_EXPECTED_RELEASE_ID"),
    mode,
  );
  const expectedCommitSha = normalizedExpectedCommitSha(
    configuredValue("WINDOPS_BACKEND_EXPECTED_COMMIT_SHA"),
    mode,
  );
  const expectedImageDigest = normalizedExpectedImageDigest(
    configuredValue("WINDOPS_BACKEND_EXPECTED_IMAGE_DIGEST"),
    mode,
  );
  if (mode === "production" && !baseUrl) {
    throw new ProductionRuntimeError(
      "BACKEND_NOT_CONFIGURED",
      "Production mode requires WINDOPS_BACKEND_BASE_URL.",
      500,
    );
  }
  return {
    mode,
    authMode,
    baseUrl,
    apiToken,
    delegationSecret,
    timeoutMs,
    expectedReleaseId,
    expectedCommitSha,
    expectedImageDigest,
  };
}

export function requireProductionBackend(): ProductionBackendConfig & {
  readonly baseUrl: string;
} {
  const config = getProductionBackendConfig();
  if (!config.baseUrl) {
    throw new ProductionRuntimeError(
      "BACKEND_NOT_CONFIGURED",
      "The production backend URL is not configured.",
    );
  }
  return { ...config, baseUrl: config.baseUrl };
}

export function productionBackendRequestTimeoutMs(
  backendPath: string,
  configuredTimeoutMs: number,
): number {
  return pathTimeoutsMs.get(backendPath) ?? configuredTimeoutMs;
}

export function isAllowedProductionGatewayPath(path: string): boolean {
  return allowedGatewayPaths.some((pattern) => pattern.test(path));
}

export function isAllowedProductionGatewayRequest(method: string, path: string): boolean {
  if (!isAllowedProductionGatewayPath(path)) return false;
  if (
    /^\/api\/v1\/(?:models\/deployments\/[A-Za-z0-9][A-Za-z0-9._-]{2,63}\/anomaly-predictions\/run|model-predictions\/[A-Za-z0-9][A-Za-z0-9._-]{2,63}\/alert-evaluation)$/.test(
      path,
    )
  ) {
    return method.toUpperCase() === "POST";
  }
  if (/^\/api\/v1\/benchmarks\/evaluations\/[^/]+\/exports$/.test(path)) {
    return method.toUpperCase() === "POST";
  }
  if (path.startsWith("/api/v1/benchmarks/")) {
    return method.toUpperCase() === "GET";
  }
  if (
    /^\/api\/v1\/platform\/(?:configuration-security-audits|data-source-security-audits)\/[^/]+\/rotation-confirmation$/.test(
      path,
    )
  ) {
    return method.toUpperCase() === "POST";
  }
  return true;
}

function errorResponse(error: ProductionRuntimeError): Response {
  return Response.json(
    {
      data: null,
      error: { code: error.code, message: error.message },
      meta: { runtimeMode: "production", fixtureFallback: false },
    },
    { status: error.status, headers: { "cache-control": "no-store" } },
  );
}

/**
 * Fail closed in production until a route has been migrated to the Python
 * backend. This prevents deterministic fixtures from masquerading as live
 * operational data when WINDOPS_RUNTIME_MODE=production.
 */
export function enforceProductionRequestBoundary(request: Request): Response | null {
  let config: ProductionBackendConfig;
  try {
    config = getProductionBackendConfig();
  } catch (error) {
    return errorResponse(
      error instanceof ProductionRuntimeError
        ? error
        : new ProductionRuntimeError(
            "INVALID_PRODUCTION_CONFIGURATION",
            "Production configuration is invalid.",
            500,
          ),
    );
  }
  if (config.mode !== "production") return null;

  const pathname = new URL(request.url).pathname;
  if (pathname.startsWith("/ws/")) {
    return errorResponse(
      new ProductionRuntimeError(
        "PRODUCTION_REALTIME_NOT_MIGRATED",
        "The deterministic WebSocket stream is disabled in production mode.",
      ),
    );
  }
  if (
    pathname.startsWith("/api/") &&
    !migratedProductionApiExactPaths.includes(
      pathname as (typeof migratedProductionApiExactPaths)[number],
    ) &&
    !migratedProductionApiPrefixes.some(
      (prefix) =>
        pathname === prefix || pathname.startsWith(prefix.endsWith("/") ? prefix : `${prefix}/`),
    )
  ) {
    return errorResponse(
      new ProductionRuntimeError(
        "PRODUCTION_ROUTE_NOT_MIGRATED",
        `The ${pathname} API has not yet been migrated to the production backend; fixture fallback is disabled.`,
      ),
    );
  }
  return null;
}

function correlationId(request: Request): string {
  return (
    request.headers.get("x-correlation-id") ??
    request.headers.get("x-request-id") ??
    crypto.randomUUID()
  );
}

function base64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const value of bytes) binary += String.fromCharCode(value);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

function encodedJson(value: unknown): string {
  return base64Url(new TextEncoder().encode(JSON.stringify(value)));
}

async function sha256Hex(value: ArrayBuffer | undefined): Promise<string> {
  const bytes = value ? new Uint8Array(value) : new Uint8Array();
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((item) => item.toString(16).padStart(2, "0")).join("");
}

async function sitesDelegationToken(
  request: Request,
  config: ProductionBackendConfig,
  requestTarget: string,
  body: ArrayBuffer | undefined,
): Promise<string> {
  const subject = request.headers.get("oai-authenticated-user-id")?.trim();
  if (!subject || !config.delegationSecret) {
    throw new ProductionRuntimeError(
      "UNAUTHENTICATED",
      subject
        ? "The Sites delegation secret is not configured."
        : "A Sites authenticated user is required.",
      401,
    );
  }
  const now = Math.floor(Date.now() / 1000);
  const email = request.headers.get("oai-authenticated-user-email")?.trim() || undefined;
  const header = encodedJson({ alg: "HS256", typ: "JWT" });
  const payload = encodedJson({
    iss: "windops-sites-gateway",
    aud: "windops-python-backend",
    sub: subject,
    email,
    iat: now,
    exp: now + 60,
    jti: crypto.randomUUID(),
    method: request.method.toUpperCase(),
    target: requestTarget,
    body_sha256: await sha256Hex(body),
  });
  const unsigned = `${header}.${payload}`;
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(config.delegationSecret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(unsigned));
  return `${unsigned}.${base64Url(new Uint8Array(signature))}`;
}

async function forwardedHeaders(
  request: Request,
  config: ProductionBackendConfig,
  requestTarget: string,
  body: ArrayBuffer | undefined,
): Promise<Headers> {
  const bearer =
    config.authMode === "sites_delegation"
      ? await sitesDelegationToken(request, config, requestTarget, body)
      : config.apiToken;
  if (!bearer) {
    throw new ProductionRuntimeError(
      "UNAUTHENTICATED",
      "The backend service token is not configured.",
      401,
    );
  }
  const headers = new Headers({
    accept: request.headers.get("accept") ?? "application/json",
    authorization: `Bearer ${bearer}`,
    "x-correlation-id": correlationId(request),
    "x-windops-runtime-mode": "production",
  });
  for (const name of [
    "content-type",
    "idempotency-key",
    "if-match",
    "last-event-id",
    "traceparent",
    "tracestate",
  ]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const userId = request.headers.get("oai-authenticated-user-id");
  const userEmail = request.headers.get("oai-authenticated-user-email");
  if (userId) headers.set("x-windops-user-id", userId);
  if (userEmail) headers.set("x-windops-user-email", userEmail);
  return headers;
}

function observedReleaseFromHeaders(headers: Headers): ProductionBackendRelease | null {
  const releaseId = headers.get("x-windops-release-id")?.trim() ?? "";
  const commitSha = headers.get("x-windops-commit-sha")?.trim() ?? "";
  const imageDigest = headers.get("x-windops-image-digest")?.trim() ?? "";
  if (
    !/^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$/.test(releaseId) ||
    !/^(?:[0-9a-f]{40}|[0-9a-f]{64})$/.test(commitSha) ||
    !/^sha256:[0-9a-f]{64}$/.test(imageDigest) ||
    imageDigest === `sha256:${"0".repeat(64)}`
  ) {
    return null;
  }
  return { releaseId, commitSha, imageDigest };
}

function releaseMismatch(
  observed: ProductionBackendRelease,
  config: ProductionBackendConfig,
): boolean {
  return (
    observed.releaseId !== config.expectedReleaseId ||
    observed.commitSha !== config.expectedCommitSha ||
    observed.imageDigest !== config.expectedImageDigest
  );
}

function responseHeaders(upstream: Response): Headers {
  const headers = new Headers();
  for (const name of [
    "content-type",
    "cache-control",
    "etag",
    "last-modified",
    "retry-after",
    "idempotency-replayed",
    "x-accel-buffering",
    "x-windops-release-id",
    "x-windops-commit-sha",
    "x-windops-image-digest",
  ]) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  headers.set("x-windops-backend", "python-fastapi");
  headers.set("x-content-type-options", "nosniff");
  return headers;
}

export async function proxyProductionBackendRequest(
  request: Request,
  backendPath: string,
): Promise<Response> {
  if (!isAllowedProductionGatewayRequest(request.method, backendPath)) {
    return errorResponse(
      new ProductionRuntimeError(
        "BACKEND_PATH_NOT_ALLOWED",
        "The requested backend path is not exposed by the production gateway.",
        404,
      ),
    );
  }

  if (
    /^\/api\/v1\/(?:models\/deployments\/[A-Za-z0-9][A-Za-z0-9._-]{2,63}\/anomaly-predictions\/run|model-predictions\/[A-Za-z0-9][A-Za-z0-9._-]{2,63}\/alert-evaluation)$/.test(
      backendPath,
    )
  ) {
    const idempotencyKey = request.headers.get("idempotency-key")?.trim() ?? "";
    if (
      backendPath.endsWith("/anomaly-predictions/run") &&
      request.headers.get("content-type")?.split(";", 1)[0]?.trim() !== "application/json"
    ) {
      return errorResponse(
        new ProductionRuntimeError(
          "INVALID_ANOMALY_COMMAND_CONTENT_TYPE",
          "Governed anomaly commands require an application/json request body.",
          415,
        ),
      );
    }
    if (idempotencyKey.length < 8 || idempotencyKey.length > 128) {
      return errorResponse(
        new ProductionRuntimeError(
          "INVALID_ANOMALY_COMMAND_IDEMPOTENCY_KEY",
          "Governed anomaly commands require an Idempotency-Key of 8 to 128 characters.",
          400,
        ),
      );
    }
  }

  let config: ReturnType<typeof requireProductionBackend>;
  try {
    config = requireProductionBackend();
  } catch (error) {
    return errorResponse(
      error instanceof ProductionRuntimeError
        ? error
        : new ProductionRuntimeError(
            "BACKEND_NOT_CONFIGURED",
            "The production backend is not configured.",
          ),
    );
  }

  const contentLength = Number(request.headers.get("content-length") ?? "0");
  if (Number.isFinite(contentLength) && contentLength > MAX_GATEWAY_BODY_BYTES) {
    return errorResponse(
      new ProductionRuntimeError(
        "BACKEND_REQUEST_TOO_LARGE",
        `Gateway request bodies are limited to ${MAX_GATEWAY_BODY_BYTES} bytes.`,
        413,
      ),
    );
  }

  const method = request.method.toUpperCase();
  const body = method === "GET" || method === "HEAD" ? undefined : await request.arrayBuffer();
  if (body && body.byteLength > MAX_GATEWAY_BODY_BYTES) {
    return errorResponse(
      new ProductionRuntimeError(
        "BACKEND_REQUEST_TOO_LARGE",
        `Gateway request bodies are limited to ${MAX_GATEWAY_BODY_BYTES} bytes.`,
        413,
      ),
    );
  }

  const sourceUrl = new URL(request.url);
  const requestTarget = `${backendPath}${sourceUrl.search}`;
  const upstreamUrl = `${config.baseUrl}${requestTarget}`;
  let headers: Headers;
  try {
    headers = await forwardedHeaders(request, config, requestTarget, body);
  } catch (error) {
    return errorResponse(
      error instanceof ProductionRuntimeError
        ? error
        : new ProductionRuntimeError("UNAUTHENTICATED", "Authentication is required.", 401),
    );
  }
  const controller = new AbortController();
  const requestTimeoutMs = productionBackendRequestTimeoutMs(backendPath, config.timeoutMs);
  const timeout = setTimeout(() => controller.abort(), requestTimeoutMs);
  try {
    const upstream = await fetch(upstreamUrl, {
      method,
      headers,
      body,
      redirect: "manual",
      signal: controller.signal,
    });
    const observedRelease = observedReleaseFromHeaders(upstream.headers);
    if (!observedRelease) {
      return errorResponse(
        new ProductionRuntimeError(
          "BACKEND_RELEASE_IDENTITY_MISSING",
          "The production backend did not provide a valid immutable release identity.",
        ),
      );
    }
    if (releaseMismatch(observedRelease, config)) {
      return errorResponse(
        new ProductionRuntimeError(
          "BACKEND_RELEASE_MISMATCH",
          "The production backend release does not match the approved Sites configuration.",
        ),
      );
    }
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders(upstream),
    });
  } catch (error) {
    const timedOut = error instanceof DOMException && error.name === "AbortError";
    return errorResponse(
      new ProductionRuntimeError(
        timedOut ? "BACKEND_TIMEOUT" : "BACKEND_UNAVAILABLE",
        timedOut
          ? "The production backend did not respond before the configured deadline."
          : "The production backend is unavailable.",
        503,
      ),
    );
  } finally {
    clearTimeout(timeout);
  }
}

export async function probeProductionBackend(): Promise<{
  readonly configured: boolean;
  readonly reachable: boolean;
  readonly status: number | null;
  readonly latencyMs: number | null;
  readonly errorCode: string | null;
  readonly release: ProductionBackendRelease | null;
}> {
  let config: ReturnType<typeof requireProductionBackend>;
  try {
    config = requireProductionBackend();
  } catch (error) {
    return {
      configured: false,
      reachable: false,
      status: null,
      latencyMs: null,
      errorCode: error instanceof ProductionRuntimeError ? error.code : "BACKEND_NOT_CONFIGURED",
      release: null,
    };
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), config.timeoutMs);
  const startedAt = Date.now();
  try {
    const response = await fetch(`${config.baseUrl}/api/v1/readyz`, {
      headers: { accept: "application/json" },
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) {
      return {
        configured: true,
        reachable: false,
        status: response.status,
        latencyMs: Date.now() - startedAt,
        errorCode: "BACKEND_NOT_READY",
        release: null,
      };
    }
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    const releaseValue =
      body && typeof body === "object" && "release" in body
        ? (body as { release?: unknown }).release
        : null;
    const releaseRecord =
      releaseValue && typeof releaseValue === "object"
        ? (releaseValue as Record<string, unknown>)
        : null;
    const release = releaseRecord
      ? observedReleaseFromHeaders(
          new Headers({
            "x-windops-release-id": asText(releaseRecord.release_id),
            "x-windops-commit-sha": asText(releaseRecord.commit_sha),
            "x-windops-image-digest": asText(releaseRecord.image_digest),
          }),
        )
      : null;
    if (!release) {
      return {
        configured: true,
        reachable: false,
        status: response.status,
        latencyMs: Date.now() - startedAt,
        errorCode: "BACKEND_RELEASE_IDENTITY_MISSING",
        release: null,
      };
    }
    if (releaseMismatch(release, config)) {
      return {
        configured: true,
        reachable: false,
        status: response.status,
        latencyMs: Date.now() - startedAt,
        errorCode: "BACKEND_RELEASE_MISMATCH",
        release,
      };
    }
    return {
      configured: true,
      reachable: true,
      status: response.status,
      latencyMs: Date.now() - startedAt,
      errorCode: null,
      release,
    };
  } catch (error) {
    return {
      configured: true,
      reachable: false,
      status: null,
      latencyMs: Date.now() - startedAt,
      errorCode:
        error instanceof DOMException && error.name === "AbortError"
          ? "BACKEND_TIMEOUT"
          : "BACKEND_UNAVAILABLE",
      release: null,
    };
  } finally {
    clearTimeout(timeout);
  }
}
