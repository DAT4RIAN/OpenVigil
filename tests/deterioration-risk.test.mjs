import assert from "node:assert/strict";
import test from "node:test";
import { deteriorationRiskLabel, deteriorationRiskPercent } from "../lib/deterioration-risk.ts";

test("unknown, malformed and out-of-range risk never becomes zero or a percentage label", () => {
  for (const value of [null, undefined, "12", false, {}, NaN, Infinity, -1, 101]) {
    assert.equal(deteriorationRiskPercent(value), null);
    assert.equal(deteriorationRiskLabel(value), "未评估");
  }
});

test("existing valid probability values remain readable, including a real zero", () => {
  for (const value of [0, 12, 12.5, 100]) {
    assert.equal(deteriorationRiskPercent(value), value);
    assert.equal(deteriorationRiskLabel(value), `${value}%`);
  }
});
