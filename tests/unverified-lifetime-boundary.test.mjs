import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);
const coreSources = [
  "components/pages/dashboard-page.tsx",
  "components/pages/turbine-detail-page.tsx",
  "components/pages/asset-health-page.tsx",
  "components/pages/digital-twin-page.tsx",
  "components/pages/diagnosis-center-page.tsx",
  "components/pages/predictive-maintenance-page.tsx",
  "components/layout/app-shell.tsx",
  "lib/operations-data.ts",
  "lib/diagnosis-data.ts",
  "lib/health-data.ts",
  "lib/telemetry-data.ts",
  "lib/generic-subsystem-data.ts",
  "lib/digital-twin-data.ts",
  "lib/agent-data.ts",
  "lib/report-data.ts",
  "lib/platform-admin-data.ts",
  "app/api/predictive-assessments/fixtures.ts",
  "app/api/predictive-assessments/route.ts",
  "app/predictive-maintenance/page.tsx",
];

const contents = await Promise.all(
  coreSources.map(async (path) => [path, await readFile(new URL(path, root), "utf8")]),
);

test("core operations do not present precise lifetime or failure-probability conclusions", () => {
  const forbiddenConclusion =
    /预计\s*RUL|预计剩余寿命|30\s*[天日]\s*失效概率|失效概率\s*(?:为\s*)?\d|RUL\s*(?:为\s*)?\d|剩余寿命\s*(?:为\s*)?\d/i;
  for (const [path, source] of contents) {
    assert.doesNotMatch(source, forbiddenConclusion, path);
  }
});

test("core fixture and API contracts cannot carry synthetic lifetime fields", () => {
  const contractSources = contents.filter(([path]) =>
    [
      "lib/operations-data.ts",
      "lib/health-data.ts",
      "lib/telemetry-data.ts",
      "lib/generic-subsystem-data.ts",
      "lib/digital-twin-data.ts",
      "app/api/predictive-assessments/fixtures.ts",
      "app/api/predictive-assessments/route.ts",
    ].includes(path),
  );
  for (const [path, source] of contractSources) {
    assert.doesNotMatch(
      source,
      /failureProbability30d|remainingUsefulLifeDays|probabilityBand|rulDays|EV-023-RUL/,
      path,
    );
  }
});

test("the demo Agent tool catalog does not expose unvalidated lifetime inference", async () => {
  const runtime = await readFile(new URL("lib/agent-tool-runtime.ts", root), "utf8");
  assert.doesNotMatch(runtime, /name:\s*["']predict_rul["']/);
  assert.doesNotMatch(runtime, /predictedRulDays|failureProbability30d/);
});

test("the production Agent workflow ranks condition evidence without synthetic lifetime output", async () => {
  const paths = [
    "backend/src/windops_backend/agents/tools.py",
    "backend/src/windops_backend/agents/graph.py",
    "backend/src/windops_backend/services/agent_governance.py",
    "backend/src/windops_backend/services/seed.py",
  ];
  const sources = await Promise.all(
    paths.map(async (path) => [path, await readFile(new URL(path, root), "utf8")]),
  );

  assert.match(sources.map(([, source]) => source).join("\n"), /assess_condition_evidence/);
  for (const [path, source] of sources) {
    assert.doesNotMatch(source, /predict_rul|estimated_rul_days|failure_probability_30d/, path);
  }
});

test("the governed model form explains the external-model boundary next to its contract", async () => {
  const modelPage = await readFile(
    new URL("components/pages/model-management-page.tsx", root),
    "utf8",
  );
  assert.match(modelPage, /CARE\s*不验证这些能力/);
  assert.match(modelPage, /Demo[\s\S]{0,80}不会生成或展示此类结论/);
});
