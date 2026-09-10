import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import { evaluateBundle, measureBundle } from "../scripts/check-bundle-budget.mjs";

async function withChunks(files, assertion) {
  const root = await mkdtemp(path.join(tmpdir(), "windops-bundle-budget-"));
  try {
    for (const [relativePath, bytes] of Object.entries(files)) {
      const filePath = path.join(root, relativePath);
      await mkdir(path.dirname(filePath), { recursive: true });
      await writeFile(filePath, Buffer.alloc(bytes));
    }
    await assertion(root);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
}

test("bundle budget measures nested JavaScript chunks without counting maps", async () => {
  await withChunks(
    { "route-a.js": 40, "nested/route-b.js": 70, "nested/route-b.js.map": 500 },
    async (root) => {
      const measurement = await measureBundle(root);
      assert.equal(measurement.chunks.length, 2);
      assert.equal(measurement.totalBytes, 110);
      assert.equal(path.basename(measurement.chunks[0].filePath), "route-b.js");
      assert.deepEqual(
        evaluateBundle(measurement, {
          maximumChunkBytes: 70,
          maximumTotalBytes: 110,
          maximumChunksOver500KiB: 0,
        }),
        [],
      );
    },
  );
});

test("bundle budget reports chunk, total, and large-chunk regressions", async () => {
  await withChunks({ "route-a.js": 600 * 1024, "route-b.js": 550 * 1024 }, async (root) => {
    const failures = evaluateBundle(await measureBundle(root), {
      maximumChunkBytes: 575 * 1024,
      maximumTotalBytes: 1100 * 1024,
      maximumChunksOver500KiB: 1,
    });
    assert.equal(failures.length, 3);
    assert.ok(failures.some((failure) => failure.includes("largest chunk")));
    assert.ok(failures.some((failure) => failure.includes("totals")));
    assert.ok(failures.some((failure) => failure.includes("exceed 500 KiB")));
  });
});

test("bundle budget fails closed when the build emitted no JavaScript", async () => {
  await withChunks({}, async (root) => {
    assert.deepEqual(
      evaluateBundle(await measureBundle(root), {
        maximumChunkBytes: 1,
        maximumTotalBytes: 1,
        maximumChunksOver500KiB: 0,
      }),
      ["no JavaScript chunks were found"],
    );
  });
});
