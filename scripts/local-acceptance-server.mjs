import { readFile, realpath } from "node:fs/promises";
import { createServer } from "node:https";
import { extname, resolve, sep } from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { pathToFileURL } from "node:url";
import { localIdentity } from "./local-identity.mjs";
import { verifiedLocalWrites } from "./local-acceptance-policy.mjs";

const mime = {
  ".css": "text/css",
  ".js": "text/javascript",
  ".json": "application/json",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
  ".ico": "image/x-icon",
};

export async function startLocalGateway(config, worker) {
  const origin = new URL(config.origin);
  const backend = new URL(config.environment.WINDOPS_BACKEND_BASE_URL);
  if (
    origin.origin !== config.origin ||
    origin.protocol !== "https:" ||
    origin.hostname !== "127.0.0.1" ||
    !origin.port ||
    backend.protocol !== "https:" ||
    backend.hostname !== "127.0.0.1" ||
    config.environment.WINDOPS_RUNTIME_MODE !== "production" ||
    config.environment.WINDOPS_BACKEND_AUTH_MODE !== "sites_delegation"
  )
    throw new Error("Invalid local gateway configuration");
  const authenticate = localIdentity({ origin: config.origin, users: config.users });
  const businessWrites = await verifiedLocalWrites(config);
  const clientRoot = await realpath(config.clientRoot);
  const assets = {
    async fetch(request) {
      let target;
      try {
        target = await realpath(
          resolve(
            clientRoot,
            decodeURIComponent(new URL(request.url).pathname).replace(/^\/+/, ""),
          ),
        );
        if (!target.startsWith(clientRoot + sep)) return new Response("Not found", { status: 404 });
        return new Response(await readFile(target), {
          headers: {
            "content-type": mime[extname(target)] ?? "application/octet-stream",
            "cache-control": "no-cache",
            "x-content-type-options": "nosniff",
          },
        });
      } catch {
        return new Response("Not found", { status: 404 });
      }
    },
  };
  const environment = { ...config.environment, ASSETS: assets };
  const context = {
    waitUntil(promise) {
      promise.catch(() => process.stderr.write("Local background request failed\n"));
    },
    passThroughOnException() {},
  };
  const server = createServer(
    {
      key: await readFile(config.tlsKey),
      cert: await readFile(config.tlsCert),
      requestTimeout: 30_000,
      headersTimeout: 15_000,
      maxHeaderSize: 16_384,
    },
    async (req, res) => {
      try {
        if (
          req.headers.host !== origin.host ||
          !req.url?.startsWith("/") ||
          req.url.startsWith("//")
        ) {
          res.writeHead(400);
          res.end("Invalid local host");
          return;
        }
        const chunks = [];
        let length = 0;
        for await (const chunk of req) {
          length += chunk.length;
          if (length > 2 * 1024 * 1024) {
            res.writeHead(413);
            res.end("Request too large");
            return;
          }
          chunks.push(chunk);
        }
        const headers = new Headers();
        for (const [key, value] of Object.entries(req.headers))
          if (value !== undefined)
            headers.set(key, Array.isArray(value) ? value.join(", ") : value);
        const method = req.method ?? "GET";
        const request = new Request(new URL(req.url, origin), {
          method,
          headers,
          body: ["GET", "HEAD"].includes(method) ? undefined : Buffer.concat(chunks),
        });
        const auth = await authenticate(request);
        let response = auth.response;
        const pathname = new URL(request.url).pathname;
        if (
          !response &&
          ["GET", "HEAD"].includes(method) &&
          (pathname.startsWith("/_next/static/") ||
            pathname.startsWith("/assets/") ||
            /\.(?:css|gif|ico|jpe?g|js|json|png|svg|webp|woff2?)$/i.test(pathname))
        ) {
          response = await assets.fetch(auth.request);
        }
        if (!response && !businessWrites && !["GET", "HEAD", "OPTIONS"].includes(method)) {
          response = Response.json(
            {
              error: {
                code: "LOCAL_ACCEPTANCE_WRITES_BLOCKED",
                message: "模型尚未通过验收门槛，当前仅开放登录和只读权限验收。",
              },
            },
            { status: 503 },
          );
        }
        if (!response) response = await worker.fetch(auth.request, environment, context);
        res.statusCode = response.status;
        response.headers.forEach((value, name) => res.setHeader(name, value));
        res.setHeader("x-windops-acceptance-scope", "local");
        res.setHeader("cache-control", "no-store");
        if (method === "HEAD" || !response.body) res.end();
        else await pipeline(Readable.fromWeb(response.body), res);
      } catch {
        if (!res.headersSent)
          res.writeHead(500, { "content-type": "text/plain", "cache-control": "no-store" });
        res.end("Local gateway request failed");
      }
    },
  );
  await new Promise((ok, reject) => {
    server.once("error", reject);
    server.listen(Number(origin.port), "127.0.0.1", ok);
  });
  return server;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const config = JSON.parse(await readFile(process.argv[2], "utf8"));
  // Verify the real API's exact candidate identity; never synthesize API release headers.
  const expected = config.environment;
  const ready = await fetch(`${expected.WINDOPS_BACKEND_BASE_URL}/api/v1/readyz`, {
    signal: AbortSignal.timeout(10_000),
  });
  if (
    !ready.ok ||
    ready.headers.get("x-windops-acceptance-scope") !== "local" ||
    ready.headers.get("x-windops-release-id") !== expected.WINDOPS_BACKEND_EXPECTED_RELEASE_ID ||
    ready.headers.get("x-windops-commit-sha") !== expected.WINDOPS_BACKEND_EXPECTED_COMMIT_SHA ||
    ready.headers.get("x-windops-image-digest") !== expected.WINDOPS_BACKEND_EXPECTED_IMAGE_DIGEST
  ) {
    throw new Error("Real local candidate identity/readiness verification failed");
  }
  const { default: worker } = await import(pathToFileURL(resolve(config.workerPath)).href);
  const server = await startLocalGateway(config, worker);
  process.stdout.write(
    `OpenVigil local acceptance gateway ${config.origin} (business writes ${config.businessAcceptance ? "enabled for local acceptance" : "blocked"})\n`,
  );
  for (const signal of ["SIGINT", "SIGTERM"])
    process.on(signal, () => server.close(() => process.exit(0)));
}
