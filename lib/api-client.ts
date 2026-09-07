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

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, {
    headers: { accept: "application/json" },
    signal,
  });
  const payload = (await response.json()) as T & {
    error?: { code?: string; message?: string };
  };
  if (!response.ok) {
    throw new WindOpsApiError(
      response.status,
      payload.error?.code ?? "API_ERROR",
      payload.error?.message ?? `WindOps API returned ${response.status}`,
    );
  }
  return payload;
}
