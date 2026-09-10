import { proxyProductionBackendRequest } from "@/lib/production-runtime";

interface BackendGatewayContext {
  readonly params: Promise<{ readonly path: readonly string[] }>;
}

async function proxy(request: Request, context: BackendGatewayContext): Promise<Response> {
  const { path } = await context.params;
  if (
    !Array.isArray(path) ||
    !path.length ||
    path.some((part) => !/^[A-Za-z0-9._:-]+$/.test(part))
  ) {
    return Response.json(
      {
        data: null,
        error: { code: "INVALID_BACKEND_PATH", message: "The backend path is invalid." },
        meta: { fixtureFallback: false },
      },
      { status: 400, headers: { "cache-control": "no-store" } },
    );
  }
  return proxyProductionBackendRequest(
    request,
    `/api/v1/${path.map(encodeURIComponent).join("/")}`,
  );
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
