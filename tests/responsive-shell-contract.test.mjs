import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

test("the shell implements the tablet, laptop, and mobile interaction contracts", async () => {
  const styleFiles = (await readdir(new URL("app/styles/", root))).sort();
  const [shell, css] = await Promise.all([
    readFile(new URL("components/layout/app-shell.tsx", root), "utf8"),
    Promise.all(
      styleFiles.map((file) => readFile(new URL(`app/styles/${file}`, root), "utf8")),
    ).then((parts) => parts.join("\n")),
  ]);

  assert.match(shell, /openvigil-sidebar-collapsed/);
  assert.match(shell, /legacySidebarPreferenceKey = "windops-sidebar-collapsed"/);
  assert.match(shell, /themePreferenceKey = "openvigil-theme"/);
  assert.match(shell, /legacyThemePreferenceKey = "windops-theme"/);
  assert.match(shell, /\(max-width: 1023px\)/);
  assert.match(shell, /\(min-width: 1024px\) and \(max-width: 1439px\)/);
  assert.match(shell, /aria-modal=/);
  assert.match(shell, /aria-expanded=/);
  assert.match(shell, /inert=/);
  assert.match(css, /@media \(max-width: 1023px\)/);
  assert.match(css, /@media \(max-width: 767px\)[\s\S]*?min-height: 44px !important/);
  assert.match(css, /@media \(max-width: 767px\)[\s\S]*?min-width: 44px !important/);
});

test("dialog focus traversal excludes CSS-hidden controls", async () => {
  const hook = await readFile(new URL("lib/use-accessible-dialog.ts", root), "utf8");
  assert.match(hook, /style\.display !== "none"/);
  assert.match(hook, /style\.visibility !== "hidden"/);
  assert.match(hook, /getClientRects\(\)\.length > 0/);
  assert.match(hook, /restoreTarget\?\.focus\(\)/);
});
