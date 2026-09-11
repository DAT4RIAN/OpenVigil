import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import ts from "typescript";

const repositoryRoot = path.resolve(import.meta.dirname, "..");
const sourceRoots = ["app", "build", "components", "db", "lib", "worker"];
const sourceExtensions = [".ts", ".tsx", ".js", ".mjs"];

const normalizePath = (filePath) => path.relative(repositoryRoot, filePath).replaceAll("\\", "/");

const collectSources = (relativeRoot) => {
  const root = path.join(repositoryRoot, relativeRoot);
  const files = [];
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    const entryPath = path.join(root, entry.name);
    if (entry.isDirectory()) files.push(...collectSources(normalizePath(entryPath)));
    else if (sourceExtensions.some((extension) => entry.name.endsWith(extension))) {
      files.push(entryPath);
    }
  }
  return files;
};

const sourceFiles = sourceRoots.flatMap(collectSources);
const sourceSet = new Set(sourceFiles.map((filePath) => path.resolve(filePath)));

const resolveInternalImport = (fromFile, specifier) => {
  let base;
  if (specifier.startsWith("@/")) base = path.join(repositoryRoot, specifier.slice(2));
  else if (specifier.startsWith(".")) base = path.resolve(path.dirname(fromFile), specifier);
  else return null;

  const extensionless = sourceExtensions.some((extension) => base.endsWith(extension))
    ? [base]
    : [base, ...sourceExtensions.map((extension) => `${base}${extension}`)];
  const candidates = [
    ...extensionless,
    ...sourceExtensions.map((extension) => path.join(base, `index${extension}`)),
  ];
  return (
    candidates
      .map((candidate) => path.resolve(candidate))
      .find((candidate) => sourceSet.has(candidate)) ?? null
  );
};

const graph = new Map(
  sourceFiles.map((filePath) => {
    const source = readFileSync(filePath, "utf8");
    const dependencies = ts
      .preProcessFile(source, true, true)
      .importedFiles.map(({ fileName }) => resolveInternalImport(filePath, fileName))
      .filter(Boolean);
    return [path.resolve(filePath), [...new Set(dependencies)]];
  }),
);

const findCycles = () => {
  const state = new Map();
  const stack = [];
  const cycles = [];

  const visit = (node) => {
    state.set(node, 1);
    stack.push(node);
    for (const dependency of graph.get(node) ?? []) {
      if (!state.has(dependency)) visit(dependency);
      else if (state.get(dependency) === 1) {
        const start = stack.indexOf(dependency);
        cycles.push([...stack.slice(start), dependency].map(normalizePath));
      }
    }
    stack.pop();
    state.set(node, 2);
  };

  for (const node of graph.keys()) if (!state.has(node)) visit(node);
  return cycles;
};

const runtimeRoots = sourceFiles.filter((filePath) => {
  const relativePath = normalizePath(filePath);
  return (
    /^app\/(?:.*\/)?(?:page|route)\.tsx?$/.test(relativePath) ||
    [
      "app/chatgpt-auth.ts",
      "app/error.tsx",
      "app/layout.tsx",
      "app/loading.tsx",
      "app/not-found.tsx",
      "build/sites-vite-plugin.ts",
      "db/schema.ts",
      "lib/index.ts",
      "worker/index.ts",
    ].includes(relativePath)
  );
});

const runtimeReachableModules = () => {
  const reachable = new Set();
  const pending = [...runtimeRoots];
  while (pending.length > 0) {
    const current = pending.pop();
    if (!current || reachable.has(current)) continue;
    reachable.add(current);
    pending.push(...(graph.get(current) ?? []));
  }
  return reachable;
};

test("application runtime modules bypass the broad lib barrel", () => {
  const forbiddenImports = sourceFiles
    .filter((filePath) => /^(app|components)\//.test(normalizePath(filePath)))
    .flatMap((filePath) => {
      const source = readFileSync(filePath, "utf8");
      return /(?:from\s+|import\s*\()(["'])@\/lib\1/.test(source) ? [normalizePath(filePath)] : [];
    });

  assert.deepEqual(forbiddenImports, []);
});

test("the compatibility barrel contains re-exports only", () => {
  const barrelPath = path.join(repositoryRoot, "lib", "index.ts");
  const sourceFile = ts.createSourceFile(
    barrelPath,
    readFileSync(barrelPath, "utf8"),
    ts.ScriptTarget.Latest,
    true,
  );

  assert.ok(sourceFile.statements.length > 0);
  assert.ok(sourceFile.statements.every((statement) => ts.isExportDeclaration(statement)));
});

test("the TypeScript runtime dependency graph remains acyclic", () => {
  assert.deepEqual(findCycles(), []);
});

test("every TypeScript source module is reachable from a runtime or build root", () => {
  const reachable = runtimeReachableModules();
  assert.deepEqual(
    sourceFiles
      .filter((filePath) => !reachable.has(filePath))
      .map(normalizePath)
      .sort(),
    [],
  );
});

test("the application page and Worker route inventories remain stable", () => {
  const inventoryHash = (files) =>
    createHash("sha256").update(files.map(normalizePath).sort().join("\n")).digest("hex");
  const pages = sourceFiles.filter((filePath) => normalizePath(filePath).endsWith("/page.tsx"));
  const routes = sourceFiles.filter((filePath) => normalizePath(filePath).endsWith("/route.ts"));

  assert.equal(pages.length, 22);
  assert.equal(
    inventoryHash(pages),
    "84b674dd7ef3300972960504ee610e6662bd3abaa74ad0d4d3fa453c613d4a51",
  );
  assert.equal(routes.length, 38);
  assert.equal(
    inventoryHash(routes),
    "0d6083f5ca5a43e4a1ff27638db5649eb32a41123712588330245290e2597fbb",
  );
});
