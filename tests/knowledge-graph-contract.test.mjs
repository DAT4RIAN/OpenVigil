import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workerUrl = new URL("../dist/server/index.js", import.meta.url);
workerUrl.searchParams.set("knowledge-graph-test", `${process.pid}-${Date.now()}`);
const { default: worker } = await import(workerUrl.href);

const environment = {
  ASSETS: {
    fetch: async () => new Response("Not found", { status: 404 }),
  },
};

const context = {
  waitUntil() {},
  passThroughOnException() {},
};

function fetchRoute(path, headers = {}) {
  return worker.fetch(
    new Request(new URL(path, "http://localhost"), { headers }),
    environment,
    context,
  );
}

test("knowledge graph proxy fails explicitly when the Python backend is not configured", async () => {
  const response = await fetchRoute("/api/knowledge-graph", { accept: "application/json" });
  assert.equal(response.status, 503);
  const body = await response.json();
  assert.equal(body.error.code, "KNOWLEDGE_GRAPH_NOT_CONFIGURED");
  assert.match(body.error.message, /Python 知识图谱服务/);
});

test("knowledge graph workspace is routable and no longer marked as coming soon", async () => {
  const response = await fetchRoute("/knowledge-graph", { accept: "text/html" });
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /故障知识图谱/);
  assert.match(html, /PostgreSQL 权威源/);
  assert.match(html, /不投影原始 SCADA/);

  const shell = await readFile(
    new URL("../components/layout/app-shell.tsx", import.meta.url),
    "utf8",
  );
  assert.match(shell, /href: "\/knowledge-graph"/);
  assert.doesNotMatch(shell, /href: "#graph"/);
});

test("worker route proxies knowledge graph reads with the standard response shape", async () => {
  const route = await readFile(
    new URL("../app/api/knowledge-graph/route.ts", import.meta.url),
    "utf8",
  );
  assert.match(route, /\/knowledge-graph\/summary/);
  assert.match(route, /\/knowledge-graph\/entities\//);
  assert.match(route, /\/knowledge-graph\/search\?query=/);
  assert.match(route, /mode === "search"/);
  assert.match(route, /proxiedFrom: "python-fastapi"/);
  assert.doesNotMatch(route, /fixture|fallback/i);
});

test("knowledge graph route uses the standard production gateway proxy", async () => {
  const route = await readFile(
    new URL("../app/api/knowledge-graph/route.ts", import.meta.url),
    "utf8",
  );
  // 生产模式统一走网关代理：Sites 委托令牌、release 钉验与超时由代理层完成。
  assert.match(route, /from "@\/lib\/production-runtime"/);
  assert.match(route, /getProductionBackendConfig/);
  assert.match(route, /proxyProductionBackendRequest/);
  // 生产模式不得默认演示实体，缺 entityId 必须显式失败。
  assert.doesNotMatch(route, /WT-023/);
  assert.match(route, /INVALID_GRAPH_ENTITY/);
  // 不得残留绕过网关的直连 env/token 读取；demo 直连的令牌来自统一配置。
  assert.doesNotMatch(route, /WINDOPS_BACKEND_BASE_URL/);
  assert.doesNotMatch(route, /WINDOPS_BACKEND_API_TOKEN/);
  assert.doesNotMatch(route, /getWorkerEnv/);
  assert.doesNotMatch(route, /graphBackendConfiguration/);
  assert.match(route, /authorization: `Bearer \$\{token\}`/);
  assert.doesNotMatch(route, /fixture|fallback/i);
});

test("knowledge graph workspace exposes explainable hybrid retrieval", async () => {
  const page = await readFile(
    new URL("../components/pages/knowledge-graph-page.tsx", import.meta.url),
    "utf8",
  );
  assert.match(page, /向量召回 \+ 图关系扩展/);
  assert.match(page, /vectorScore/);
  assert.match(page, /graphScore/);
  assert.match(page, /graphExpansion\.paths/);
  assert.match(page, /不生成无证据结论/);
});
