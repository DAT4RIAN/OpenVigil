import { createHash } from "node:crypto";
import { readFile, realpath } from "node:fs/promises";
import { dirname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const artifactRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../.artifacts");
const sha = (data) => createHash("sha256").update(data).digest("hex");

async function boundArtifact(path, expected) {
  if (typeof path !== "string" || !/^[a-f0-9]{64}$/.test(expected ?? ""))
    throw new Error("Invalid local acceptance evidence reference");
  const [root, file] = await Promise.all([realpath(artifactRoot), realpath(path)]);
  if (!file.startsWith(root + sep)) throw new Error("Evidence must stay in project artifacts");
  const bytes = await readFile(file);
  if (sha(bytes) !== expected) throw new Error("Local acceptance evidence changed");
  return JSON.parse(bytes.toString("utf8"));
}

/** A qualified model and matching built source are required before local business writes. */
export async function verifiedLocalWrites(config) {
  const receipt = config.businessAcceptance;
  if (receipt === undefined) return false;
  if (!receipt || typeof receipt !== "object") throw new Error("Invalid acceptance receipt");
  const decision = await boundArtifact(receipt.qualificationFile, receipt.qualificationSha256);
  const build = await boundArtifact(receipt.buildReportFile, receipt.buildReportSha256);
  const expected = config.environment;
  if (
    decision.status !== "MODEL_QUALIFIED_FOR_LOCAL_WORKFLOW_PROBE" ||
    decision.eligible_for_local_promotion !== true ||
    decision.production_release !== false ||
    decision.diagnosis?.passed !== true ||
    decision.diagnosis?.accuracy !== 1 ||
    decision.diagnosis?.citation_precision !== 1 ||
    decision.diagnosis?.required_citation_recall !== 1 ||
    decision.diagnosis?.case_count !== 6 ||
    !Number.isFinite(decision.diagnosis?.p95_seconds) ||
    decision.diagnosis.p95_seconds < 0 ||
    decision.diagnosis?.p95_seconds > 20 ||
    decision.budget?.unknown_reserve_cny !== "0" ||
    !Number.isFinite(decision.workflow_latency_seconds?.alternatives) ||
    !Number.isFinite(decision.workflow_latency_seconds?.reviews) ||
    decision.workflow_latency_seconds.alternatives < 0 ||
    decision.workflow_latency_seconds.alternatives > 45 ||
    decision.workflow_latency_seconds.reviews < 0 ||
    decision.workflow_latency_seconds.reviews > 90 ||
    build.status !== "built" ||
    build.release_id !== expected.WINDOPS_BACKEND_EXPECTED_RELEASE_ID ||
    build.commit_sha !== expected.WINDOPS_BACKEND_EXPECTED_COMMIT_SHA ||
    build.image_manifest_digest !== expected.WINDOPS_BACKEND_EXPECTED_IMAGE_DIGEST
  )
    throw new Error("Qualified local model or candidate identity mismatch");
  const plan = await boundArtifact(
    resolve(dirname(receipt.qualificationFile), "plan.json"),
    decision.evidence_sha256?.["plan.json"],
  );
  const params = plan.parameters;
  if (
    plan.model !== "openai/deepseek-ai/DeepSeek-V4-Flash" ||
    plan.model !== expected.WINDOPS_BACKEND_EXPECTED_REASONING_MODEL ||
    params?.enable_thinking !== false ||
    params?.max_retries !== 0 ||
    params?.timeout_seconds !== 45 ||
    params?.review_timeout_seconds !== 90 ||
    params?.diagnosis_p95_seconds !== 20
  )
    throw new Error("Local reasoning profile mismatch");
  for (const path of [
    "src/windops_backend/agents/reasoning.py",
    "src/windops_backend/config.py",
    "src/windops_backend/operations/reasoning_eval.py",
  ]) {
    if (
      !/^[a-f0-9]{64}$/.test(build.source_files?.[path] ?? "") ||
      build.source_files[path] !== plan.source_inputs?.["backend/" + path]
    )
      throw new Error("Qualified reasoning source differs from candidate image");
  }
  return true;
}
