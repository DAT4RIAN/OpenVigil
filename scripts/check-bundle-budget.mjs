import { readdir, stat } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

export const bundleBudget = Object.freeze({
  maximumChunkBytes: 675 * 1024,
  maximumTotalBytes: 2700 * 1024,
  maximumChunksOver500KiB: 1,
});

async function listJavaScriptFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(
    entries.map(async (entry) => {
      const entryPath = path.join(directory, entry.name);
      if (entry.isDirectory()) return listJavaScriptFiles(entryPath);
      return entry.isFile() && entry.name.endsWith(".js") ? [entryPath] : [];
    }),
  );
  return nested.flat();
}

export async function measureBundle(chunksDirectory) {
  const files = await listJavaScriptFiles(chunksDirectory);
  const chunks = await Promise.all(
    files.map(async (filePath) => ({
      filePath,
      bytes: (await stat(filePath)).size,
    })),
  );
  chunks.sort((left, right) => right.bytes - left.bytes);
  return {
    chunks,
    totalBytes: chunks.reduce((total, chunk) => total + chunk.bytes, 0),
    chunksOver500KiB: chunks.filter((chunk) => chunk.bytes > 500 * 1024).length,
  };
}

export function evaluateBundle(measurement, budget = bundleBudget) {
  const failures = [];
  const largestChunk = measurement.chunks[0];
  if (!largestChunk) failures.push("no JavaScript chunks were found");
  if (largestChunk && largestChunk.bytes > budget.maximumChunkBytes) {
    failures.push(
      `largest chunk ${path.basename(largestChunk.filePath)} is ${largestChunk.bytes} bytes; ` +
        `budget is ${budget.maximumChunkBytes} bytes`,
    );
  }
  if (measurement.totalBytes > budget.maximumTotalBytes) {
    failures.push(
      `client JavaScript totals ${measurement.totalBytes} bytes; ` +
        `budget is ${budget.maximumTotalBytes} bytes`,
    );
  }
  if (measurement.chunksOver500KiB > budget.maximumChunksOver500KiB) {
    failures.push(
      `${measurement.chunksOver500KiB} chunks exceed 500 KiB; ` +
        `budget permits ${budget.maximumChunksOver500KiB}`,
    );
  }
  return failures;
}

export async function main(chunksDirectory = "dist/client/_next/static/chunks") {
  const measurement = await measureBundle(chunksDirectory);
  const failures = evaluateBundle(measurement);
  if (failures.length) {
    for (const failure of failures) console.error(`BUNDLE BUDGET FAILED: ${failure}`);
    return 1;
  }
  const largest = measurement.chunks[0];
  console.log(
    `Bundle budget passed: ${measurement.chunks.length} chunks, ` +
      `${measurement.totalBytes} bytes total, largest ${path.basename(largest.filePath)} ` +
      `at ${largest.bytes} bytes`,
  );
  return 0;
}

if (process.argv[1] && pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url) {
  process.exitCode = await main(process.argv[2]);
}
