import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

test("shared buttons expose a restrained glass material and all eight states", async () => {
  const [styles, component, preview] = await Promise.all([
    readFile(new URL("app/styles/15-button-glass.css", root), "utf8"),
    readFile(new URL("components/ui/primitives.tsx", root), "utf8"),
    readFile(new URL("components/ui/Button.preview.html", root), "utf8"),
  ]);

  for (const marker of [
    "backdrop-filter",
    "linear-gradient",
    ":focus-visible",
    ":active",
    ":disabled",
    '[data-state="loading"]',
    '[data-state="error"]',
    '[data-state="success"]',
    "@media (hover: hover) and (pointer: fine)",
    "@media (prefers-reduced-motion: reduce)",
    "@media (prefers-reduced-transparency: reduce)",
  ]) {
    assert.match(styles, new RegExp(marker.replaceAll(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }

  assert.match(component, /aria-busy=\{loading \|\| undefined\}/);
  assert.match(component, /disabled=\{loading \|\| props\.disabled\}/);
  assert.match(component, /data-state=\{state\}/);
  assert.match(component, /type ButtonStatus = "error" \| "success"/);

  for (const state of [
    "default",
    "hover",
    "focus-visible",
    "active",
    "disabled",
    "loading",
    "error",
    "success",
  ]) {
    assert.match(preview, new RegExp(`>${state}<|data-state="${state}"`));
  }
  assert.match(preview, /\bdisabled\b/);
});
