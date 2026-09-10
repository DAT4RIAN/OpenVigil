/** WindOps Sites 网关入口：托管 vinext 前端，并将生产 API 请求统一代理到 Python 后端。 */
import {
  handleImageOptimization,
  DEFAULT_DEVICE_SIZES,
  DEFAULT_IMAGE_SIZES,
} from "vinext/server/image-optimization";
import handler from "vinext/server/app-router-entry";
import { runWithWorkerEnv, type WindOpsWorkerEnv } from "../lib/worker-env";
import {
  enforceProductionRequestBoundary,
  getProductionBackendConfig,
} from "../lib/production-runtime";
import { authorizeProductionDocument } from "../lib/production-shell-auth";

const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "base-uri 'self'",
  "connect-src 'self'",
  "font-src 'self' data:",
  "form-action 'self'",
  "frame-ancestors 'none'",
  "frame-src 'none'",
  "img-src 'self' data: blob:",
  "media-src 'self' blob:",
  "object-src 'none'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "worker-src 'self' blob:",
].join("; ");

function withSecurityHeaders(request: Request, response: Response, production: boolean): Response {
  if (response.status === 101) return response;
  const headers = new Headers(response.headers);
  headers.set("content-security-policy", CONTENT_SECURITY_POLICY);
  headers.set("cross-origin-opener-policy", "same-origin");
  headers.set("cross-origin-resource-policy", "same-origin");
  headers.set("permissions-policy", "camera=(), geolocation=(), microphone=(), payment=(), usb=()");
  headers.set("referrer-policy", "no-referrer");
  headers.set("x-content-type-options", "nosniff");
  headers.set("x-frame-options", "DENY");
  if (production && new URL(request.url).protocol === "https:") {
    headers.set("strict-transport-security", "max-age=63072000; includeSubDomains; preload");
  }
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

interface Env extends WindOpsWorkerEnv {
  readonly ASSETS?: Fetcher;
  readonly DB?: D1Database;
  readonly IMAGES?: {
    input(stream: ReadableStream): {
      transform(options: Record<string, unknown>): {
        output(options: { format: string; quality: number }): Promise<{ response(): Response }>;
      };
    };
  };
}

function normalizeWorkerEnv(env: Env | undefined): Env {
  return env ?? {};
}

function productionModeRequested(env: Env): boolean {
  const processMode = typeof process === "undefined" ? undefined : process.env.WINDOPS_RUNTIME_MODE;
  return (env.WINDOPS_RUNTIME_MODE ?? processMode)?.trim().toLowerCase() === "production";
}

interface ExecutionContext {
  waitUntil(promise: Promise<unknown>): void;
  passThroughOnException(): void;
}

// Image security config. SVG sources with .svg extension auto-skip the
// optimization endpoint on the client side (served directly, no proxy).
// To route SVGs through the optimizer (with security headers), set
// dangerouslyAllowSVG: true in next.config.js and uncomment below:
// const imageConfig: ImageConfig = { dangerouslyAllowSVG: true };

const worker = {
  async fetch(
    originalRequest: Request,
    env: Env | undefined,
    ctx: ExecutionContext,
  ): Promise<Response> {
    const runtimeEnv = normalizeWorkerEnv(env);
    return runWithWorkerEnv(runtimeEnv, async () => {
      const productionRequested = productionModeRequested(runtimeEnv);
      const boundaryResponse = enforceProductionRequestBoundary(originalRequest);
      if (boundaryResponse) {
        return withSecurityHeaders(originalRequest, boundaryResponse, productionRequested);
      }
      // The boundary above validates the full configuration and converts every
      // failure into a structured response, so this second read cannot throw.
      const production = getProductionBackendConfig().mode === "production";
      const authorization = production
        ? await authorizeProductionDocument(originalRequest)
        : { request: originalRequest, response: null };
      if (authorization.response) {
        return withSecurityHeaders(originalRequest, authorization.response, production);
      }
      const request = authorization.request ?? originalRequest;

      const url = new URL(request.url);

      if (url.pathname === "/_vinext/image") {
        if (!runtimeEnv.ASSETS || !runtimeEnv.IMAGES) {
          return withSecurityHeaders(
            request,
            Response.json(
              {
                data: null,
                error: {
                  code: "IMAGE_BINDINGS_NOT_CONFIGURED",
                  message: "Image optimization bindings are not configured for this runtime.",
                },
                meta: { runtimeMode: production ? "production" : "demo" },
              },
              { status: 503, headers: { "cache-control": "no-store" } },
            ),
            production,
          );
        }
        const allowedWidths = [...DEFAULT_DEVICE_SIZES, ...DEFAULT_IMAGE_SIZES];
        const response = await handleImageOptimization(
          request,
          {
            fetchAsset: (path) => runtimeEnv.ASSETS!.fetch(new Request(new URL(path, request.url))),
            transformImage: async (body, { width, format, quality }) => {
              const result = await runtimeEnv
                .IMAGES!.input(body)
                .transform(width > 0 ? { width } : {})
                .output({ format, quality });
              return result.response();
            },
          },
          allowedWidths,
        );
        return withSecurityHeaders(request, response, production);
      }

      const response = await handler.fetch(request, runtimeEnv, ctx);
      return withSecurityHeaders(request, response, production);
    });
  },
};

export default worker;
