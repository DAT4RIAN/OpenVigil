import { proxyProductionBackendRequest } from "../production-runtime.ts";

export type JsonRecord = Record<string, unknown>;

export const isRecord = (value: unknown): value is JsonRecord =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export const text = (value: unknown, fallback = ""): string =>
  typeof value === "string" ? value : fallback;

export const number = (value: unknown, fallback = 0): number =>
  typeof value === "number" && Number.isFinite(value) ? value : fallback;

export const list = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);

export const record = (value: unknown): JsonRecord => (isRecord(value) ? value : {});

export type BackendCollectionResult = {
  upstream: Response;
  rows: JsonRecord[];
  total: number | null;
  nextCursor: string | null;
  complete: boolean;
};

export function jsonError(code: string, message: string, status = 502): Response {
  return Response.json(
    {
      data: null,
      error: { code, message },
      meta: { runtimeMode: "production", fixtureFallback: false },
    },
    { status, headers: { "cache-control": "no-store" } },
  );
}

export async function backendCollection(
  request: Request,
  backendPath: string,
  key: string,
): Promise<BackendCollectionResult | Response> {
  const upstream = await proxyProductionBackendRequest(request, backendPath);
  if (!upstream.ok) return upstream;
  let payload: unknown;
  try {
    payload = await upstream.json();
  } catch {
    return jsonError("INVALID_BACKEND_RESPONSE", "The production backend returned invalid JSON.");
  }
  const envelope = isRecord(payload) ? payload : {};
  const rawRows = envelope[key];
  if (!Array.isArray(rawRows) || !rawRows.every(isRecord)) {
    return jsonError(
      "INVALID_BACKEND_RESPONSE",
      `The production backend response did not contain a valid ${key} collection.`,
    );
  }
  const rows = rawRows;
  const rawNextCursor = envelope.next_cursor;
  const nextCursor =
    typeof rawNextCursor === "string" && rawNextCursor.length > 0 ? rawNextCursor : null;
  const backendMeta = record(envelope.meta);
  const rawTotal =
    typeof envelope.total === "number"
      ? envelope.total
      : typeof backendMeta.total === "number"
        ? backendMeta.total
        : null;
  const complete = nextCursor === null;
  return {
    upstream,
    rows,
    total: rawTotal ?? (complete ? rows.length : null),
    nextCursor,
    complete,
  };
}

export function collectionResponse(
  data: JsonRecord[],
  upstream: Response,
  collection?: Pick<BackendCollectionResult, "total" | "nextCursor" | "complete">,
): Response {
  const total = collection ? collection.total : data.length;
  const nextCursor = collection?.nextCursor ?? null;
  const hasMore = collection ? !collection.complete : false;
  return Response.json(
    {
      data,
      meta: {
        count: data.length,
        total,
        nextCursor,
        hasMore,
        runtimeMode: "production",
        source: "python-fastapi",
        fixtureFallback: false,
      },
    },
    {
      headers: {
        "cache-control": "no-store",
        "x-windops-backend": upstream.headers.get("x-windops-backend") ?? "python-fastapi",
      },
    },
  );
}
