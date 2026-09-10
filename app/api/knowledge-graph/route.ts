import { errorResponse, jsonResponse } from "@/app/api/_shared";
import {
  getProductionBackendConfig,
  proxyProductionBackendRequest,
} from "@/lib/production-runtime";

type BackendGraphResponse = {
  readonly data?: unknown;
  readonly meta?: Record<string, unknown>;
  readonly error?: { readonly code?: string; readonly message?: string };
};

type BackendReadResult =
  | { readonly ok: true; readonly body: BackendGraphResponse }
  | { readonly ok: false; readonly response: Response };

type BackendReader = (path: string) => Promise<BackendReadResult>;

async function parseBackendBody(response: Response): Promise<BackendGraphResponse | null> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function upstreamErrorResponse(status: number, body: BackendGraphResponse | null): Response {
  return jsonResponse(
    {
      error: body?.error ?? {
        code: "KNOWLEDGE_GRAPH_UPSTREAM_ERROR",
        message: "知识图谱服务暂时无法完成查询。",
      },
    },
    status,
  );
}

function invalidBackendRead(): BackendReadResult {
  return {
    ok: false,
    response: errorResponse(
      "KNOWLEDGE_GRAPH_BAD_RESPONSE",
      "知识图谱后端返回了无法解析的响应。",
      502,
    ),
  };
}

// 生产模式：后端调用统一经过网关代理，每次调用独立签发 Sites 委托令牌、
// 钉验 release ID 与镜像摘要并受网关超时约束，任何一步失败都会关闭请求。
async function readProductionBackend(request: Request, path: string): Promise<BackendReadResult> {
  const separator = path.indexOf("?");
  const resource = separator === -1 ? path : path.slice(0, separator);
  const url = new URL(request.url);
  url.search = separator === -1 ? "" : path.slice(separator + 1);
  const upstream = await proxyProductionBackendRequest(
    new Request(url, request),
    `/api/v1${resource}`,
  );
  const body = await parseBackendBody(upstream);
  if (!upstream.ok) return { ok: false, response: upstreamErrorResponse(upstream.status, body) };
  if (!body) return invalidBackendRead();
  return { ok: true, body };
}

// Demo 模式：该路由没有本地演示数据，必须连接真实 Python 知识图谱服务，
// 沿用环境配置的服务令牌直连本地 FastAPI。
async function readDemoBackend(
  baseUrl: string,
  token: string,
  path: string,
): Promise<BackendReadResult> {
  let response: Response;
  try {
    response = await fetch(`${baseUrl}/api/v1${path}`, {
      headers: {
        accept: "application/json",
        authorization: `Bearer ${token}`,
      },
      cache: "no-store",
    });
  } catch {
    return {
      ok: false,
      response: errorResponse(
        "KNOWLEDGE_GRAPH_UNAVAILABLE",
        "无法连接 Python 知识图谱服务，请检查 FastAPI 与 Neo4j 运行状态。",
        503,
      ),
    };
  }
  const body = await parseBackendBody(response);
  if (!response.ok) return { ok: false, response: upstreamErrorResponse(response.status, body) };
  if (!body) return invalidBackendRead();
  return { ok: true, body };
}

async function knowledgeGraphResponse(request: Request, read: BackendReader): Promise<Response> {
  const url = new URL(request.url);
  const mode = url.searchParams.get("mode")?.trim() || "graph";
  const entityId = url.searchParams.get("entityId")?.trim() ?? "";
  const requestedDepth = Number(url.searchParams.get("depth") ?? "4");
  const depth = Number.isInteger(requestedDepth) ? Math.max(1, Math.min(4, requestedDepth)) : 4;
  if (entityId.length > 160) {
    return errorResponse("INVALID_GRAPH_ENTITY", "entityId 不能超过 160 个字符。", 400);
  }

  if (mode === "search") {
    const query = url.searchParams.get("query")?.trim() ?? "";
    if (query.length < 3 || query.length > 500) {
      return errorResponse("INVALID_GRAPH_QUERY", "检索问题长度必须为 3 到 500 个字符。", 400);
    }
    const result = await read(
      `/knowledge-graph/search?query=${encodeURIComponent(query)}${
        entityId ? `&entityId=${encodeURIComponent(entityId)}` : ""
      }`,
    );
    if (!result.ok) return result.response;
    return jsonResponse({
      ...result.body,
      meta: {
        ...result.body.meta,
        ...(entityId ? { entityId } : {}),
        proxiedFrom: "python-fastapi",
      },
    });
  }

  if (mode !== "graph") {
    return errorResponse("INVALID_GRAPH_MODE", "mode 仅支持 graph 或 search。", 400);
  }
  if (!entityId) {
    return errorResponse(
      "INVALID_GRAPH_ENTITY",
      "graph 模式必须提供 entityId 查询参数，请在页面检索框输入真实实体。",
      400,
    );
  }

  const [summary, graph] = await Promise.all([
    read("/knowledge-graph/summary"),
    read(`/knowledge-graph/entities/${encodeURIComponent(entityId)}/subgraph?depth=${depth}`),
  ]);
  if (!summary.ok) return summary.response;
  if (!graph.ok) return graph.response;
  return jsonResponse({
    data: {
      summary: summary.body.data,
      graph: graph.body.data,
    },
    meta: {
      ...summary.body.meta,
      entityId,
      depth,
      proxiedFrom: "python-fastapi",
    },
  });
}

export async function GET(request: Request): Promise<Response> {
  const config = getProductionBackendConfig();
  if (config.mode === "production") {
    return knowledgeGraphResponse(request, (path) => readProductionBackend(request, path));
  }
  const { baseUrl, apiToken } = config;
  if (!baseUrl || !apiToken) {
    return errorResponse(
      "KNOWLEDGE_GRAPH_NOT_CONFIGURED",
      "尚未配置 Python 知识图谱服务地址或服务端访问令牌。",
      503,
    );
  }
  return knowledgeGraphResponse(request, (path) => readDemoBackend(baseUrl, apiToken, path));
}
