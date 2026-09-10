import { publishApiAccessFailure, type ApiAccessFailure } from "./api-access-events.ts";

export class WindOpsApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "WindOpsApiError";
    this.status = status;
    this.code = code;
  }
}

function failureKind(status: number): ApiAccessFailure["kind"] | null {
  if (status === 401) return "authentication";
  if (status === 403) return "authorization";
  if (status === 503) return "backend";
  return null;
}

async function parseResponse<T>(response: Response): Promise<T> {
  const payload = (await response.json()) as T & {
    error?: { code?: string; message?: string };
  };
  if (!response.ok) {
    const error = new WindOpsApiError(
      response.status,
      payload.error?.code ?? "API_ERROR",
      payload.error?.message ?? `WindOps API returned ${response.status}`,
    );
    const kind = failureKind(response.status);
    if (kind) {
      publishApiAccessFailure({
        kind,
        status: response.status,
        code: error.code,
        message: error.message,
      });
    }
    throw error;
  }
  return payload;
}

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      headers: { accept: "application/json" },
      signal,
    });
  } catch (error) {
    if (!signal?.aborted) {
      publishApiAccessFailure({
        kind: "network",
        status: null,
        code: "NETWORK_FAILURE",
        message: "无法连接 WindOps 服务。",
      });
    }
    throw error;
  }
  return parseResponse<T>(response);
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
    } catch (retryError) {
      publishApiAccessFailure({
        kind: "network",
        status: null,
        code: "NETWORK_FAILURE",
        message: "命令传输重试后仍无法连接 WindOps 服务。",
      });
      throw retryError;
    }
  }
}

export async function apiPost<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const response = await postWithNetworkRetry(
    path,
    JSON.stringify(body),
    {
      accept: "application/json",
      "content-type": "application/json",
      "idempotency-key": createIdempotencyKey(),
    },
    signal,
  );
  return parseResponse<T>(response);
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
  return parseResponse<T>(response);
}
