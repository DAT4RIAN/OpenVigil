import {
  publishApiAccessFailure,
  publishApiAccessRecovery,
  type ApiAccessFailure,
} from "./api-access-events.ts";

export class OpenVigilApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly correlationId: string | null;
  readonly operationKey: string | null;

  constructor(
    status: number,
    code: string,
    message: string,
    correlationId: string | null = null,
    operationKey: string | null = null,
  ) {
    super(message);
    this.name = "OpenVigilApiError";
    this.status = status;
    this.code = code;
    this.correlationId = correlationId;
    this.operationKey = operationKey;
  }
}

function failureKind(status: number): ApiAccessFailure["kind"] | null {
  if (status === 401) return "authentication";
  if (status === 403) return "authorization";
  if (status === 503) return "backend";
  return null;
}

async function parseResponse<T>(
  response: Response,
  requestCorrelationId?: string,
  scope?: string,
  operationKey?: string | null,
): Promise<T> {
  const payload = (await response.json()) as T & {
    error?: { code?: string; message?: string };
    meta?: { correlationId?: string; correlation_id?: string };
  };
  if (!response.ok) {
    const error = new OpenVigilApiError(
      response.status,
      payload.error?.code ?? "API_ERROR",
      payload.error?.message ?? `OpenVigil API returned ${response.status}`,
      response.headers.get("x-correlation-id") ??
        payload.meta?.correlationId ??
        payload.meta?.correlation_id ??
        requestCorrelationId ??
        null,
      operationKey ?? null,
    );
    const kind = failureKind(response.status);
    if (kind) {
      publishApiAccessFailure({
        kind,
        status: response.status,
        code: error.code,
        message: error.message,
        scope,
        operationKey,
      });
    }
    throw error;
  }
  return payload;
}

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  const correlationId = `read-${globalThis.crypto.randomUUID()}`;
  try {
    response = await fetch(path, {
      headers: { accept: "application/json", "x-correlation-id": correlationId },
      signal,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    const networkError = new OpenVigilApiError(
      0,
      "NETWORK_FAILURE",
      "无法连接 OpenVigil 服务。",
      correlationId,
    );
    publishApiAccessFailure({
      kind: "network",
      status: null,
      code: networkError.code,
      message: networkError.message,
      scope: path,
    });
    throw networkError;
  }
  const payload = await parseResponse<T>(response, correlationId, path);
  publishApiAccessRecovery({ scope: path });
  return payload;
}

export function createIdempotencyKey(scope = "windops-command"): string {
  return `${scope}-${globalThis.crypto.randomUUID()}`;
}

async function postWithNetworkRetry(
  path: string,
  body: string,
  headers: HeadersInit,
  signal?: AbortSignal,
): Promise<Response> {
  const send = () =>
    fetch(path, {
      method: "POST",
      headers,
      body,
      signal,
    });
  try {
    return await send();
  } catch (error) {
    if (signal?.aborted) throw error;
    // A transport failure can happen after the backend committed. The same
    // key makes this single retry a response replay instead of a second side effect.
    try {
      return await send();
    } catch {
      const operationKey = new Headers(headers).get("idempotency-key");
      const unknownError = new OpenVigilApiError(
        0,
        "COMMAND_RESULT_UNKNOWN",
        "命令传输重试后仍未收到权威响应；后端可能已提交，请使用同一幂等键核验结果。",
        null,
        operationKey,
      );
      publishApiAccessFailure({
        kind: "network",
        status: null,
        code: unknownError.code,
        message: unknownError.message,
        scope: path,
        operationKey,
      });
      throw unknownError;
    }
  }
}

export async function apiPost<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const operationKey = createIdempotencyKey();
  const response = await postWithNetworkRetry(
    path,
    JSON.stringify(body),
    {
      accept: "application/json",
      "content-type": "application/json",
      "idempotency-key": operationKey,
    },
    signal,
  );
  const payload = await parseResponse<T>(response, undefined, path, operationKey);
  publishApiAccessRecovery({ scope: path, operationKey });
  return payload;
}

export async function apiPostCommand<T>(
  path: string,
  body: unknown,
  idempotencyKey: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await postWithNetworkRetry(
    path,
    JSON.stringify(body),
    {
      accept: "application/json",
      "content-type": "application/json",
      "idempotency-key": idempotencyKey,
    },
    signal,
  );
  const payload = await parseResponse<T>(response, undefined, path, idempotencyKey);
  publishApiAccessRecovery({ scope: path, operationKey: idempotencyKey });
  return payload;
}
