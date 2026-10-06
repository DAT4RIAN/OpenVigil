import assert from "node:assert/strict";
import test from "node:test";

// Vinext retains the fetch function present when its cache shim loads.
// Install a dispatching fixture before importing the compiled Worker so route
// handlers and middleware use the same controlled backend transport.
const nativeFetch = globalThis.fetch;
let activeFetch;
globalThis.fetch = (...args) => (activeFetch ? activeFetch(...args) : nativeFetch(...args));
const workerUrl = new URL("../dist/server/index.js", import.meta.url);
workerUrl.searchParams.set("native-knowledge-test", `${process.pid}-${Date.now()}`);
const { default: worker } = await import(workerUrl.href);
const releaseId = "windops-knowledge-contract";
const commitSha = "a".repeat(40);
const imageDigest = `sha256:${"b".repeat(64)}`;
const productionEnvironment = {
  ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) },
  WINDOPS_RUNTIME_MODE: "production",
  WINDOPS_BACKEND_AUTH_MODE: "sites_delegation",
  WINDOPS_BACKEND_BASE_URL: "https://windops-backend.example",
  WINDOPS_BACKEND_DELEGATION_SECRET:
    "knowledge-worker-contract-secret-with-at-least-forty-eight-characters",
  WINDOPS_BACKEND_EXPECTED_RELEASE_ID: releaseId,
  WINDOPS_BACKEND_EXPECTED_COMMIT_SHA: commitSha,
  WINDOPS_BACKEND_EXPECTED_IMAGE_DIGEST: imageDigest,
};
const context = { waitUntil() {}, passThroughOnException() {} };
function backendJson(body) {
  return Response.json(body, {
    headers: {
      "x-windops-release-id": releaseId,
      "x-windops-commit-sha": commitSha,
      "x-windops-image-digest": imageDigest,
    },
  });
}
function identitySession() {
  return {
    subject: "knowledge-manager",
    email: "operator@example.com",
    roles: ["operations_manager"],
    capabilities: ["view.knowledge"],
    scope: {
      tenant_count: 1,
      wind_farm_count: 0,
      turbine_count: 0,
      entity_count: 0,
      allow_global: false,
    },
  };
}
function sitesRequest(url, init) {
  const headers = new Headers(init.headers);
  headers.set("oai-authenticated-user-id", "knowledge-manager");
  headers.set("oai-authenticated-user-email", "operator@example.com");
  return new Request(url, { ...init, headers });
}

test("production assistant carries native passage versions and positions without inventing page one", async () => {
  const original = activeFetch;
  activeFetch = async (input) => {
    if (String(input).endsWith("/api/v1/session")) return backendJson(identitySession());
    return backendJson({
      data: {
        answerMode: "grounded-retrieval-summary-no-generative-claim",
        matches: [
          {
            match_type: "knowledge_document",
            document_id: "KB-PDF-R1",
            passage_id: "12345678-1234-4234-8234-123456789012",
            page_number: 7,
            document_version: "r1",
            title: "Synthetic PDF",
            excerpt: "Verify calibration",
            fusedScore: 0.8,
          },
          {
            match_type: "knowledge_document",
            document_id: "KB-TXT-R1",
            passage_id: "22345678-1234-4234-8234-123456789012",
            page_number: null,
            document_version: "r3",
            native_locator: { kind: "text_lines", line_start: 4, line_end: 8 },
            title: "Synthetic text",
            excerpt: "Record direct force",
            fusedScore: 0.7,
          },
        ],
      },
    });
  };
  try {
    const response = await worker.fetch(
      sitesRequest("https://windops.example/api/knowledge-assistant", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ question: "Verify synthetic retest evidence" }),
      }),
      productionEnvironment,
      context,
    );
    assert.equal(response.status, 200, await response.clone().text());
    const citations = (await response.json()).data.answer.citations;
    assert.equal(citations[0].page, 7);
    assert.equal(citations[1].page, null);
    assert.equal(citations[1].documentVersion, "r3");
    assert.deepEqual(citations[1].nativeLocator, {
      kind: "text_lines",
      line_start: 4,
      line_end: 8,
    });
    assert.match(citations[1].href, /document=KB-TXT-R1&passage=22345678/);
  } finally {
    activeFetch = original;
  }
});
