import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const modelPage = (
  await Promise.all(
    [
      "model-management-page.tsx",
      "model-management-contracts.ts",
      "model-management-support.ts",
      "use-model-management.ts",
    ].map((filename) =>
      readFile(new URL(`../components/pages/${filename}`, import.meta.url), "utf8"),
    ),
  )
).join("\n");
const modelCss = await readFile(
  new URL("../components/pages/model-management-page.module.css", import.meta.url),
  "utf8",
);
const diagnosisPage = await readFile(
  new URL("../components/pages/diagnosis-center-page.tsx", import.meta.url),
  "utf8",
);
const diagnosisCss = await readFile(
  new URL("../components/pages/diagnosis-center-page.module.css", import.meta.url),
  "utf8",
);
const productionRuntime = await readFile(
  new URL("../lib/production-runtime.ts", import.meta.url),
  "utf8",
);

test("CARE model governance reads bounded evaluations and preserves failed outcomes", () => {
  assert.match(modelPage, /\/api\/backend\/benchmarks\/evaluations\?modelId=/);
  assert.match(modelPage, /\/results\?limit=64&revealTruth=/);
  assert.match(modelPage, /evaluation_page_max/);
  assert.match(modelPage, /metrics_per_evaluation_max/);
  assert.match(modelPage, /服务器发布门槛/);
  assert.match(modelPage, /失败与不可评分事件不会隐藏/);
  assert.match(modelPage, /artifact missing|模型制品.*缺失/s);
  assert.match(modelPage, /授权已陈旧/);
  assert.match(modelPage, /release metric/);
  assert.match(modelPage, /不是经验证 RUL/);
  assert.match(modelPage, /演示模式不会用固定模型卡冒充 CARE 评估/);
});

test("CARE model page implements loading, empty, error, permission, and repeat-action states", () => {
  for (const marker of [
    "正在读取受治理评估",
    "评估 API 或权限校验失败",
    "没有可用的 CARE 评估运行",
    "当前身份没有 benchmark_truth 数据范围",
    "事件结果或真值权限请求失败",
    "该评估没有事件级结果",
  ]) {
    assert.match(modelPage, new RegExp(marker));
  }
  assert.match(modelPage, /disabled=\{benchmarkEvaluationsQuery\.isFetching\}/);
  assert.match(modelPage, /benchmarkResultsQuery\.isFetching/);
  assert.match(modelCss, /@media \(max-width: 760px\)/);
  assert.match(modelCss, /\.evaluationTabs/);
  assert.match(modelCss, /\.eventResults article/);
});

test("CARE diagnosis renders governed time, quality, prediction, threshold, and closure evidence", () => {
  assert.match(diagnosisPage, /\/api\/backend\/benchmarks\/diagnoses\?limit=16/);
  assert.match(diagnosisPage, /合成回放时间/);
  assert.match(diagnosisPage, /匿名来源时间/);
  assert.match(diagnosisPage, /quality_mask_refs/);
  assert.match(diagnosisPage, /anomaly_score/);
  assert.match(diagnosisPage, /binary_prediction/);
  assert.match(diagnosisPage, /threshold\.value/);
  assert.match(diagnosisPage, /Prediction .* Alarm/s);
  assert.match(diagnosisPage, /Mission .* Decision/s);
  assert.match(diagnosisPage, /提前行数（非 RUL）/);
  assert.match(diagnosisPage, /页面不会根据 SCADA 属性合成分数/);
  assert.doesNotMatch(diagnosisPage, /remainingUsefulLifeDays|failureProbability30d/);
});

test("CARE diagnosis fails closed across demo, empty, network, permission, and responsive states", () => {
  for (const marker of [
    "演示模式不加载 CARE fixture",
    "正在读取 PostgreSQL 回放与诊断证据",
    "CARE 诊断 API、数据域或真值权限校验失败",
    "当前授权范围没有 CARE replay diagnosis",
    "当前身份没有 benchmark_truth 数据范围",
    "artifact missing",
    "已陈旧",
    "正常抑制或连续窗口不足不会伪造 Mission",
  ]) {
    assert.match(diagnosisPage, new RegExp(marker));
  }
  assert.match(diagnosisPage, /disabled=\{[\s\S]*benchmarkDiagnosisQuery\.isFetching/);
  assert.match(diagnosisCss, /@media \(max-width: 920px\)/);
  assert.match(diagnosisCss, /@media \(max-width: 650px\)/);
  assert.match(diagnosisCss, /\.benchmarkWorkspace/);
  assert.match(productionRuntime, /api\\\/v1\\\/benchmarks/);
});
