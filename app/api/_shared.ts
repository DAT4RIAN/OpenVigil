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

export const turbineNotFoundResponse = (id: string): Response =>
  jsonResponse(
    {
      error: {
        code: "TURBINE_NOT_FOUND",
        message: `Wind turbine ${id} was not found.`,
      },
    },
    404,
  );
