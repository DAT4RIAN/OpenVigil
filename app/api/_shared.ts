const JSON_HEADERS = {
  "cache-control": "no-store",
  "content-type": "application/json; charset=utf-8",
} as const;

export const jsonResponse = <T>(body: T, status = 200): Response =>
  Response.json(body, {
    status,
    headers: JSON_HEADERS,
  });

export const collectionResponse = <T>(
  data: readonly T[],
  meta: Readonly<Record<string, unknown>> = {},
): Response =>
  jsonResponse({
    data,
    meta: {
      count: data.length,
      total: data.length,
      ...meta,
    },
  });

export const errorResponse = (code: string, message: string, status = 400): Response =>
  jsonResponse(
    {
      error: {
        code,
        message,
      },
    },
    status,
  );

export const turbineNotFoundResponse = (id: string): Response =>
  errorResponse("TURBINE_NOT_FOUND", `Wind turbine ${id} was not found.`, 404);

export const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export const isNonEmptyString = (value: unknown): value is string =>
  typeof value === "string" && value.trim().length > 0;

export const parseBoundedInteger = (
  value: string | null,
  fallback: number,
  minimum: number,
  maximum: number,
): number | null => {
  if (value === null) return fallback;
  if (!/^\d+$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= minimum && parsed <= maximum ? parsed : null;
};
