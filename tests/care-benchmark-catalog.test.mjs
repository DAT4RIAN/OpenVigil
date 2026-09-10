import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workerUrl = new URL("../dist/server/index.js", import.meta.url);
workerUrl.searchParams.set("care-benchmark-catalog-test", `${process.pid}-${Date.now()}`);
const { default: worker } = await import(workerUrl.href);

const environment = {
  ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) },
};
const context = { waitUntil() {}, passThroughOnException() {} };

const pageSource = (
  await Promise.all(
    ["data-center-page.tsx", "data-center-support.tsx", "use-data-center-workspace.ts"].map(
      (filename) => readFile(new URL(`../components/pages/${filename}`, import.meta.url), "utf8"),
    ),
  )
).join("\n");
const gatewaySource = await readFile(
  new URL("../app/api/backend/[...path]/route.ts", import.meta.url),
  "utf8",
);
const catalogRouteSource = await readFile(
  new URL("../app/api/data-catalog/route.ts", import.meta.url),
  "utf8",
);
const catalogDataSource = await readFile(
  new URL("../lib/platform-admin-data.ts", import.meta.url),
  "utf8",
);
const productionRuntimeSource = await readFile(
  new URL("../lib/production-runtime.ts", import.meta.url),
  "utf8",
);

test("CARE data center uses bounded production APIs and never fetches raw CSV", () => {
  assert.match(pageSource, /\/api\/backend\/benchmarks\/datasets\?/);
  assert.match(pageSource, /\/events\?/);
  assert.match(pageSource, /\/curve\?variable=/);
  assert.match(pageSource, /maxPoints=128/);
  assert.match(pageSource, /raw_csv_loaded/);
  assert.match(pageSource, /truth_included/);
  assert.doesNotMatch(pageSource, /CARE_To_Compare/);
  assert.deepEqual(
    [...pageSource.matchAll(/\.csv/gi)].map((match) => match[0]),
    [".csv"],
  );
  assert.match(pageSource, /filename: "openvigil-data-catalog\.csv"/);
  assert.match(gatewaySource, /proxyProductionBackendRequest/);
  assert.match(gatewaySource, /`\/api\/v1\/\$\{path/);
  assert.match(productionRuntimeSource, /api\\\/v1\\\/benchmarks/);
});

test("CARE data center implements disabled, loading, empty, error, stale, and permission states", () => {
  for (const marker of [
    "生产数据连接未启用",
    "正在读取基准元数据",
    "没有匹配的基准数据集",
    "基准目录读取失败",
    "当前暂时显示上一份有界快照",
    "无 Benchmark 数据权限",
  ]) {
    assert.match(pageSource, new RegExp(marker));
  }
  assert.match(pageSource, /instanceof OpenVigilApiError/);
  assert.match(pageSource, /status === 403/);
  assert.match(pageSource, /placeholderData: \(previous\) => previous/);
});

test("governed catalog declares benchmark category and stable pagination", async () => {
  assert.match(catalogDataSource, /"schema", "benchmark"/);
  assert.match(catalogRouteSource, /"offset", "limit"/);
  assert.match(catalogRouteSource, /parseBoundedInteger\(limitValue, 64, 1, 64\)/);
  assert.match(catalogRouteSource, /nextOffset/);
  assert.match(pageSource, /benchmark: "Benchmark"/);
  assert.match(pageSource, /benchmark: Activity/);

  const invalidLimit = await worker.fetch(
    new Request("http://openvigil.test/api/data-catalog?limit=65"),
    environment,
    context,
  );
  assert.equal(invalidLimit.status, 400);
  assert.deepEqual(await invalidLimit.json(), {
    error: {
      code: "INVALID_LIMIT",
      message: "limit must be an integer within 1..64.",
    },
  });
});
