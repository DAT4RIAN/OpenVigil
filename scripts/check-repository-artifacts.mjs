import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const policyPath = fileURLToPath(
  new URL("../docs/repository-artifact-policy.json", import.meta.url),
);
const policy = JSON.parse(readFileSync(policyPath, "utf8"));

if (policy.schema !== "windops.repository-artifact-policy.v1") {
  throw new Error(`Unsupported repository artifact policy: ${policy.schema}`);
}

const rawIndex = execFileSync("git", ["ls-files", "-s", "-z"], {
  cwd: root,
  encoding: "utf8",
  maxBuffer: 16 * 1024 * 1024,
});
const entries = rawIndex
  .split("\0")
  .filter(Boolean)
  .map((record) => {
    const match = /^(\d+) ([0-9a-f]+) (\d)\t(.+)$/.exec(record);
    if (!match) throw new Error(`Could not parse Git index record: ${record}`);
    return { mode: match[1], objectId: match[2], stage: match[3], path: match[4] };
  })
  .filter((entry) => entry.stage === "0" && entry.mode !== "160000");

const objectIds = [...new Set(entries.map((entry) => entry.objectId))];
const rawObjects = execFileSync(
  "git",
  ["cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"],
  {
    cwd: root,
    input: `${objectIds.join("\n")}\n`,
    encoding: "utf8",
    maxBuffer: 16 * 1024 * 1024,
  },
);
const sizes = new Map(
  rawObjects
    .trim()
    .split(/\r?\n/)
    .filter(Boolean)
    .map((record) => {
      const [objectId, type, size] = record.split(" ");
      if (type !== "blob") throw new Error(`Index object ${objectId} is ${type}, not a blob`);
      return [objectId, Number(size)];
    }),
);

const allowlist = new Map(
  policy.largeArtifactAllowlist.map((artifact) => [artifact.path, artifact]),
);
const forbiddenPathAllowlist = new Set(policy.forbiddenPathAllowlist ?? []);
const violations = [];
let totalBytes = 0;
let governedLargeArtifacts = 0;

for (const entry of entries) {
  const size = sizes.get(entry.objectId);
  if (!Number.isSafeInteger(size)) {
    violations.push(`${entry.path}: Git blob size is unavailable`);
    continue;
  }
  totalBytes += size;
  if (
    !forbiddenPathAllowlist.has(entry.path) &&
    (policy.forbiddenPrefixes.some((prefix) => entry.path.startsWith(prefix)) ||
      policy.forbiddenSegments.some((segment) => entry.path.includes(segment)))
  ) {
    violations.push(`${entry.path}: generated/cache path is forbidden`);
  }
  if (size <= policy.maxTrackedBlobBytes) continue;

  const exception = allowlist.get(entry.path);
  const required = ["sourceUri", "license", "sha256", "scanEvidenceUri"];
  if (!exception || required.some((field) => !exception[field])) {
    violations.push(
      `${entry.path}: ${size} bytes exceeds ${policy.maxTrackedBlobBytes} without complete provenance`,
    );
    continue;
  }
  const blob = execFileSync("git", ["cat-file", "blob", entry.objectId], {
    cwd: root,
    encoding: "buffer",
    maxBuffer: size + 1024,
  });
  const sha256 = createHash("sha256").update(blob).digest("hex");
  if (sha256 !== exception.sha256) {
    violations.push(`${entry.path}: SHA-256 does not match its governed exception`);
    continue;
  }
  governedLargeArtifacts += 1;
}

for (const path of allowlist.keys()) {
  if (!entries.some((entry) => entry.path === path)) {
    violations.push(`${path}: governed exception does not identify a tracked file`);
  }
}

if (violations.length > 0) {
  console.error("Repository artifact policy failed:");
  for (const violation of violations.slice(0, 50)) console.error(`- ${violation}`);
  if (violations.length > 50) console.error(`- ... ${violations.length - 50} more violations`);
  process.exitCode = 1;
} else {
  console.log(
    JSON.stringify({
      schema: "windops.repository-artifact-evidence.v1",
      status: "PASS",
      trackedBlobs: entries.length,
      trackedBytes: totalBytes,
      maxTrackedBlobBytes: policy.maxTrackedBlobBytes,
      governedLargeArtifacts,
    }),
  );
}
