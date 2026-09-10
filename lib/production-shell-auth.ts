import { chatGPTSignInPath, chatGPTSignOutPath } from "./auth-paths.ts";
import {
  encodeTrustedSession,
  parseBackendIdentitySession,
  TRUSTED_SESSION_HEADER,
} from "./identity-session.ts";
import { proxyProductionBackendRequest } from "./production-runtime.ts";

const AUTH_PATHS = new Set(["/signin-with-chatgpt", "/signout-with-chatgpt", "/callback"]);
const ASSET_PREFIXES = ["/_next/", "/_vinext/", "/assets/"];
const ASSET_EXTENSIONS =
  /\.(?:avif|css|gif|ico|jpe?g|js|json|map|mp3|mp4|png|svg|txt|webmanifest|webp|woff2?)$/i;

export function isProductionDocumentRequest(request: Request): boolean {
  if (request.method !== "GET" && request.method !== "HEAD") return false;
  const path = new URL(request.url).pathname;
  return (
    !path.startsWith("/api/") &&
    !path.startsWith("/ws/") &&
    !AUTH_PATHS.has(path) &&
    !ASSET_PREFIXES.some((prefix) => path.startsWith(prefix)) &&
    !ASSET_EXTENSIONS.test(path)
  );
}

function safeError(responseBody: unknown): { code: string; message: string } {
  if (typeof responseBody !== "object" || responseBody === null) {
    return { code: "SESSION_UNAVAILABLE", message: "生产身份服务暂时不可用。" };
  }
  const error = (responseBody as { error?: unknown }).error;
  if (typeof error !== "object" || error === null) {
    return { code: "SESSION_UNAVAILABLE", message: "生产身份服务暂时不可用。" };
  }
  const rawCode = (error as { code?: unknown }).code;
  const rawMessage = (error as { message?: unknown }).message;
  return {
    code:
      typeof rawCode === "string" && /^[A-Z0-9_]{2,80}$/.test(rawCode)
        ? rawCode
        : "SESSION_UNAVAILABLE",
    message:
      typeof rawMessage === "string" && rawMessage.length <= 240
        ? rawMessage
        : "生产身份服务暂时不可用。",
  };
}

function escaped(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function accessGateResponse(status: number, code: string, message: string): Response {
  const forbidden = status === 403;
  const network = status === 502 || code === "BACKEND_UNAVAILABLE";
  const title = forbidden
    ? "当前账号没有 WindOps 访问权限"
    : network
      ? "无法连接生产服务"
      : "生产服务尚未就绪";
  const action = forbidden
    ? `<a href="${chatGPTSignOutPath("/")}">退出并切换账号</a>`
    : '<a href="">重新检查</a>';
  const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title} · WindOps</title><style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f3f6f8;color:#16232b;font:16px/1.6 system-ui,sans-serif}.gate{width:min(560px,calc(100% - 32px));box-sizing:border-box;padding:32px;border:1px solid #d8e0e5;border-radius:18px;background:#fff;box-shadow:0 18px 60px #19313c14}.mark{font-weight:800;color:#087a6b;letter-spacing:.04em}.code{font:12px ui-monospace,monospace;color:#667780}.actions{display:flex;gap:12px;margin-top:24px}.actions a{display:inline-flex;padding:10px 16px;border-radius:9px;background:#087a6b;color:#fff;text-decoration:none}.actions a+ a{background:#eef3f5;color:#243640}@media(max-width:420px){.gate{padding:24px}.actions{align-items:stretch;flex-direction:column}}</style></head><body><main class="gate" data-session-gate="${status}"><div class="mark">WindOps Production</div><h1>${title}</h1><p>${escaped(message)}</p><p class="code">${escaped(code)} · HTTP ${status}</p><div class="actions">${action}<a href="${chatGPTSignOutPath("/")}">安全退出</a></div></main></body></html>`;
  return new Response(html, {
    status,
    headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" },
  });
}

export type ProductionDocumentAuthorization =
  | { readonly request: Request; readonly response: null }
  | { readonly request: null; readonly response: Response };

export async function authorizeProductionDocument(
  request: Request,
): Promise<ProductionDocumentAuthorization> {
  const sanitizedHeaders = new Headers(request.headers);
  sanitizedHeaders.delete(TRUSTED_SESSION_HEADER);
  sanitizedHeaders.delete("x-windops-capabilities");
  const sanitizedRequest = new Request(request, { headers: sanitizedHeaders });
  if (!isProductionDocumentRequest(sanitizedRequest)) {
    return { request: sanitizedRequest, response: null };
  }

  const userId = sanitizedHeaders.get("oai-authenticated-user-id")?.trim();
  if (!userId) {
    const source = new URL(request.url);
    const returnTo = `${source.pathname}${source.search}`;
    return {
      request: null,
      response: Response.redirect(new URL(chatGPTSignInPath(returnTo), request.url), 302),
    };
  }

  const sessionRequest = new Request(request.url, {
    method: "GET",
    headers: sanitizedHeaders,
  });
  const sessionResponse = await proxyProductionBackendRequest(sessionRequest, "/api/v1/session");
  let body: unknown;
  try {
    body = await sessionResponse.json();
  } catch {
    body = null;
  }
  if (sessionResponse.status === 401) {
    const source = new URL(request.url);
    return {
      request: null,
      response: Response.redirect(
        new URL(chatGPTSignInPath(`${source.pathname}${source.search}`), request.url),
        302,
      ),
    };
  }
  if (!sessionResponse.ok) {
    const error = safeError(body);
    return {
      request: null,
      response: accessGateResponse(sessionResponse.status, error.code, error.message),
    };
  }
  const session = parseBackendIdentitySession(body, userId);
  if (!session) {
    return {
      request: null,
      response: accessGateResponse(
        503,
        "INVALID_SESSION_CONTRACT",
        "生产身份服务返回了无效的 capability 合同，页面已安全停止。",
      ),
    };
  }
  sanitizedHeaders.set(TRUSTED_SESSION_HEADER, encodeTrustedSession(session));
  return {
    request: new Request(sanitizedRequest, { headers: sanitizedHeaders }),
    response: null,
  };
}
