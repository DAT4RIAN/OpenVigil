import assert from "node:assert/strict";
import test from "node:test";
import { isNavigationItemActive, navigationOwnerPath } from "../lib/navigation-ownership.ts";

test("detail routes inherit one stable navigation owner", () => {
  assert.equal(navigationOwnerPath("/missions/MISSION-42", "demo"), "/missions");
  assert.equal(navigationOwnerPath("/missions/MISSION-42?tab=evidence", "production"), "/missions");
  assert.equal(navigationOwnerPath("/turbines/WT-023", "demo"), "/turbines/WT-023");
  assert.equal(navigationOwnerPath("/turbines/WT-900", "production"), "/wind-farms");
  assert.equal(navigationOwnerPath("/decisions?status=pending", "demo"), "/decisions");
});

test("only the owning navigation item is current", () => {
  assert.equal(isNavigationItemActive("/missions/MISSION-42", "/missions", "demo"), true);
  assert.equal(isNavigationItemActive("/missions/MISSION-42", "/decisions", "demo"), false);
  assert.equal(isNavigationItemActive("/turbines/WT-900", "/wind-farms", "production"), true);
});
