import assert from "node:assert/strict";
import test from "node:test";
import { readMaintenanceReviews } from "../lib/maintenance-review.ts";

const review = {
  review_type: "safety",
  reviewer_agent: "reviewer",
  outcome: "fail",
  public_summary: "Isolation is unavailable.",
  conditions: ["Confirm isolation"],
  operating_constraints: ["Do not restart"],
};

test("maintenance review preserves failures and separates prerequisites from operating restrictions", () => {
  const state = {
    review_target: {
      scope: "maintenance_execution",
      alternative_id: "ALT-1",
      execution_plan_id: "workplan:abc",
    },
    reviews: [review],
  };
  const result = readMaintenanceReviews(state);
  assert.deepEqual(result.target, state.review_target);
  assert.equal(result.reviews[0].outcome, "fail");
  assert.deepEqual(result.reviews[0].conditions, ["Confirm isolation"]);
  assert.deepEqual(result.reviews[0].operatingConstraints, ["Do not restart"]);
  assert.equal(result.incomplete, false);
  assert.equal(state.reviews[0], review);
});

test("legacy and unknown targets are never inferred to mean maintenance permission", () => {
  const legacy = readMaintenanceReviews({ reviews: [review] });
  assert.equal(legacy.target, null);
  assert.equal(legacy.reviews[0].outcome, "fail");
  assert.equal(legacy.incomplete, false);
  const unknown = readMaintenanceReviews({
    review_target: {
      scope: "operating_permission",
      alternative_id: "ALT-1",
      execution_plan_id: null,
    },
    reviews: [review],
  });
  assert.equal(unknown.target, null);
  assert.equal(unknown.incomplete, true);
});

test("malformed records and unknown outcomes remain visibly incomplete rather than passing", () => {
  const result = readMaintenanceReviews({
    reviews: [null, { ...review, outcome: "constructor", conditions: ["Inspect", 7] }],
  });
  assert.equal(result.incomplete, true);
  assert.equal(result.reviews[0].outcome, "constructor");
  assert.deepEqual(result.reviews[0].conditions, ["Inspect"]);
  assert.deepEqual(readMaintenanceReviews({}).reviews, []);
  assert.equal(readMaintenanceReviews({ reviews: {} }).incomplete, true);
});
