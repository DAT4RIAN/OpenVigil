import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { resolve, sep } from "node:path";
import test from "node:test";
import { verifiedLocalWrites } from "../scripts/local-acceptance-policy.mjs";

const root = resolve(".artifacts/local-acceptance-policy-tests");
const sha = (data) => createHash("sha256").update(data).digest("hex");

test("business writes require unmodified qualification, profile and exact candidate source", async () => {
  await mkdir(root, { recursive: true });
  const folder = await mkdtemp(root + sep + "case-");
  try {
    const hashes = Object.fromEntries(
      [
        "src/windops_backend/agents/reasoning.py",
        "src/windops_backend/config.py",
        "src/windops_backend/operations/reasoning_eval.py",
      ].map((p) => [p, sha(p)]),
    );
    const plan = {
      model: "openai/deepseek-ai/DeepSeek-V4-Flash",
      parameters: {
        enable_thinking: false,
        max_retries: 0,
        timeout_seconds: 45,
        review_timeout_seconds: 90,
        diagnosis_p95_seconds: 20,
      },
      source_inputs: Object.fromEntries(
        Object.entries(hashes).map(([p, h]) => ["backend/" + p, h]),
      ),
    };
    const build = {
      status: "built",
      release_id: "test-release",
      commit_sha: "a".repeat(40),
      image_manifest_digest: "sha256:" + "b".repeat(64),
      source_files: hashes,
    };
    const planFile = resolve(folder, "plan.json");
    await writeFile(planFile, JSON.stringify(plan));
    const decision = {
      status: "MODEL_QUALIFIED_FOR_LOCAL_WORKFLOW_PROBE",
      eligible_for_local_promotion: true,
      production_release: false,
      diagnosis: {
        case_count: 6,
        passed: true,
        accuracy: 1,
        citation_precision: 1,
        required_citation_recall: 1,
        p95_seconds: 7,
      },
      budget: { unknown_reserve_cny: "0" },
      workflow_latency_seconds: { alternatives: 5, reviews: 25 },
      evidence_sha256: { "plan.json": sha(await readFile(planFile)) },
    };
    const qualificationFile = resolve(folder, "decision.json");
    const buildReportFile = resolve(folder, "build.json");
    const config = {
      environment: {
        WINDOPS_BACKEND_EXPECTED_RELEASE_ID: build.release_id,
        WINDOPS_BACKEND_EXPECTED_COMMIT_SHA: build.commit_sha,
        WINDOPS_BACKEND_EXPECTED_IMAGE_DIGEST: build.image_manifest_digest,
        WINDOPS_BACKEND_EXPECTED_REASONING_MODEL: plan.model,
      },
    };
    const bind = async () => {
      await writeFile(qualificationFile, JSON.stringify(decision));
      await writeFile(buildReportFile, JSON.stringify(build));
      config.businessAcceptance = {
        qualificationFile,
        buildReportFile,
        qualificationSha256: sha(await readFile(qualificationFile)),
        buildReportSha256: sha(await readFile(buildReportFile)),
      };
    };
    assert.equal(await verifiedLocalWrites(config), false);
    config.businessAcceptance = true;
    await assert.rejects(verifiedLocalWrites(config));
    await bind();
    assert.equal(await verifiedLocalWrites(config), true);
    await writeFile(qualificationFile, "{}");
    await assert.rejects(verifiedLocalWrites(config), /changed/);
    await bind();
    decision.eligible_for_local_promotion = false;
    await bind();
    await assert.rejects(verifiedLocalWrites(config), /mismatch/);
    decision.eligible_for_local_promotion = true;
    const latency = decision.diagnosis.p95_seconds;
    delete decision.diagnosis.p95_seconds;
    await bind();
    await assert.rejects(verifiedLocalWrites(config), /mismatch/);
    decision.diagnosis.p95_seconds = latency;
    config.environment.WINDOPS_BACKEND_EXPECTED_COMMIT_SHA = "c".repeat(40);
    await bind();
    await assert.rejects(verifiedLocalWrites(config), /mismatch/);
    config.environment.WINDOPS_BACKEND_EXPECTED_COMMIT_SHA = build.commit_sha;
    build.source_files["src/windops_backend/agents/reasoning.py"] = "d".repeat(64);
    await bind();
    await assert.rejects(verifiedLocalWrites(config), /differs/);
    build.source_files = {
      ...hashes,
      "src/windops_backend/agents/reasoning.py": sha("src/windops_backend/agents/reasoning.py"),
    };
    plan.parameters.review_timeout_seconds = 120;
    await writeFile(planFile, JSON.stringify(plan));
    decision.evidence_sha256["plan.json"] = sha(await readFile(planFile));
    await bind();
    await assert.rejects(verifiedLocalWrites(config), /profile/);
  } finally {
    assert.ok(folder.startsWith(root + sep));
    await rm(folder, { recursive: true });
  }
});
