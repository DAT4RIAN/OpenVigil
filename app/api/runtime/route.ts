import {
  getProductionBackendConfig,
  probeProductionBackend,
  ProductionRuntimeError,
} from "@/lib/production-runtime";

export async function GET(): Promise<Response> {
  try {
    const config = getProductionBackendConfig();
    const backend = await probeProductionBackend();
    const productionReady = config.mode === "production" && backend.reachable;
    return Response.json(
      {
        data: {
          runtimeMode: config.mode,
          backendAuthentication: config.authMode,
          productionReady,
          fixtureFallbackAllowed: config.mode === "demo",
          backend,
        },
        error: null,
        meta: { readOnly: true, secretsRedacted: true },
      },
      {
        status: config.mode === "production" && !productionReady ? 503 : 200,
        headers: { "cache-control": "no-store" },
      },
    );
  } catch (error) {
    const runtimeError =
      error instanceof ProductionRuntimeError
        ? error
        : new ProductionRuntimeError(
            "INVALID_PRODUCTION_CONFIGURATION",
            "Production configuration is invalid.",
            500,
          );
    return Response.json(
      {
        data: null,
        error: { code: runtimeError.code, message: runtimeError.message },
        meta: { readOnly: true, secretsRedacted: true, fixtureFallback: false },
      },
      { status: runtimeError.status, headers: { "cache-control": "no-store" } },
    );
  }
}
