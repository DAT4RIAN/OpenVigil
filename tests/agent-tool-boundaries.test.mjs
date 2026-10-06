import assert from "node:assert/strict";
import { before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { build } from "vite";

let runtime;
let contracts;
let catalog;
let validation;

before(async () => {
  const entries = {
    runtime: "agent-tool-runtime",
    contracts: "agent-tools/contracts",
    catalog: "agent-tools/catalog",
    validation: "agent-tools/validation",
  };
  const bundle = await build({
    configFile: false,
    logLevel: "silent",
    plugins: [
      {
        name: "agent-tool-contract-entry",
        resolveId(id) {
          return id.endsWith("virtual:agent-tool-contracts") ? "\0agent-tool-contracts" : null;
        },
        load(id) {
          if (id !== "\0agent-tool-contracts") return null;
          return (
            Object.entries(entries)
              .map(
                ([name, entry]) =>
                  `import * as ${name} from ${JSON.stringify(fileURLToPath(new URL(`../lib/${entry}.ts`, import.meta.url)))};`,
              )
              .join("\n") + `\nexport { ${Object.keys(entries).join(", ")} };`
          );
        },
      },
    ],
    build: {
      write: false,
      minify: false,
      lib: { entry: "virtual:agent-tool-contracts", formats: ["es"] },
    },
  });
  const output = (Array.isArray(bundle) ? bundle[0] : bundle).output.find(
    (item) => item.type === "chunk",
  );
  assert.ok(output);
  ({ runtime, contracts, catalog, validation } = await import(
    `data:text/javascript;base64,${Buffer.from(output.code).toString("base64")}`
  ));
});

test("the Agent tool entry retains exact contract, catalog and validator identities", () => {
  assert.equal(runtime.AGENT_TOOL_NAMES, contracts.AGENT_TOOL_NAMES);
  assert.equal(runtime.AgentToolRuntimeError, contracts.AgentToolRuntimeError);
  assert.equal(runtime.agentToolCatalog, catalog.agentToolCatalog);
  assert.equal(runtime.isAgentToolName, catalog.isAgentToolName);
  assert.equal(runtime.getDefaultAgentIdForTool, catalog.getDefaultAgentIdForTool);
  assert.equal(
    runtime.normalizeAgentToolExecutionRequest,
    validation.normalizeAgentToolExecutionRequest,
  );
  assert.deepEqual(
    Object.keys(runtime).sort(),
    [
      "AGENT_TOOL_NAMES",
      "AgentToolRuntimeError",
      "agentToolCatalog",
      "executeAgentTool",
      "getAgentToolExecutionHistory",
      "getDefaultAgentIdForTool",
      "isAgentToolName",
      "normalizeAgentToolExecutionRequest",
      "stableAgentToolStringify",
    ].sort(),
  );
});

test("standalone validation preserves errors and never creates an execution record", () => {
  const before = runtime.getAgentToolExecutionHistory();
  for (const [request, code, statusCode] of [
    [{ tool: "unknown", args: {} }, "UNKNOWN_AGENT_TOOL", 400],
    [{ tool: "query_scada", args: [] }, "INVALID_TOOL_ARGUMENTS", 422],
    [{ tool: "create_work_order", args: { dryRun: false } }, "INVALID_TOOL_ARGUMENTS", 422],
  ]) {
    assert.throws(
      () => validation.normalizeAgentToolExecutionRequest(request),
      (error) => {
        assert.ok(error instanceof runtime.AgentToolRuntimeError);
        assert.equal(error.code, code);
        assert.equal(error.statusCode, statusCode);
        return true;
      },
    );
  }
  assert.deepEqual(runtime.getAgentToolExecutionHistory(), before);
});

test("execution state remains single-owned after catalog and validator imports", () => {
  const request = { tool: "get_turbine_status", args: { turbineId: " wt-023 " } };
  const normalized = validation.normalizeAgentToolExecutionRequest(request);
  assert.equal(normalized.args.turbineId, "WT-023");
  const first = runtime.executeAgentTool(request);
  const detached = runtime.executeAgentTool(request, { recordInMemory: false });
  const last = runtime.executeAgentTool(request);
  assert.equal(first.result.ok, true);
  assert.deepEqual(first.result.data, detached.result.data);
  assert.deepEqual(first.result.data, last.result.data);
  assert.deepEqual(runtime.getAgentToolExecutionHistory(), [first, last]);
  assert.equal(new Date(detached.startedAt) - new Date(first.startedAt), 1000);
  assert.equal(new Date(last.startedAt) - new Date(first.startedAt), 2000);
});
