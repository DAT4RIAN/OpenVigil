import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const root = new URL("../", import.meta.url);

async function cssSources(directory) {
  const base = new URL(`${directory}/`, root);
  const entries = await readdir(base, { recursive: true });
  return Promise.all(
    entries
      .filter((entry) => entry.endsWith(".css"))
      .map(async (entry) => {
        const relativePath = path.posix.join(directory, entry.replaceAll("\\", "/"));
        return [relativePath, await readFile(new URL(relativePath, root), "utf8")];
      }),
  );
}

const appSources = await cssSources("app");
const sources = [...appSources, ...(await cssSources("components"))];
const applicationCss = appSources.map(([, source]) => source).join("\n");

test("the design system declares the required body, secondary, and metadata scale", () => {
  assert.match(applicationCss, /--font-body:\s*13px/);
  assert.match(applicationCss, /--font-secondary:\s*12px/);
  assert.match(applicationCss, /--font-metadata:\s*11px/);
  assert.match(applicationCss, /body\s*\{[\s\S]*?font-size:\s*var\(--font-body\)/);
});

test("stylesheets cannot reintroduce text below the 11px metadata floor", () => {
  const pixelFontSize = /font-size\s*:\s*([0-9]+(?:\.[0-9]+)?)px/g;
  for (const [file, source] of sources) {
    for (const match of source.matchAll(pixelFontSize)) {
      assert.ok(Number(match[1]) >= 11, `${file} contains ${match[0]}`);
    }
  }
});

test("shared business controls and tables use the semantic type scale", async () => {
  const tableCss = await readFile(
    new URL("components/data-display/data-table.module.css", root),
    "utf8",
  );
  assert.match(applicationCss, /\.button\s*\{[\s\S]*?font-size:\s*13px/);
  assert.match(applicationCss, /\.status-badge\s*\{[\s\S]*?font-size:\s*var\(--font-secondary\)/);
  assert.match(tableCss, /\.table th\s*\{[\s\S]*?font-size:\s*var\(--font-body\)/);
  assert.match(tableCss, /\.table td\s*\{[\s\S]*?font-size:\s*13px/);
});

test("canvas chart labels honor the metadata floor", async () => {
  for (const file of [
    "components/charts/time-series-chart.tsx",
    "components/charts/knowledge-graph-chart.tsx",
  ]) {
    const source = await readFile(new URL(file, root), "utf8");
    for (const match of source.matchAll(/fontSize:\s*([0-9]+(?:\.[0-9]+)?)/g)) {
      assert.ok(Number(match[1]) >= 11, `${file} contains ${match[0]}`);
    }
  }
});
