import assert from "node:assert/strict";
import test from "node:test";

import {
  canCompleteFeaturedWorkOrder,
  canonicalDemoWorkflow,
  featuredWorkOrderTaskIds,
  transitionDemoWorkflow,
} from "../lib/demo-workflow.ts";

const approval = {
  type: "submit-approval",
  action: "approve",
  approver: "李明远",
  approverRole: "值班总工程师",
  timestamp: "2026-08-13T09:02:00+08:00",
  reason: "四类审核通过",
  comment: "批准方案 B",
};

test("high-risk execution remains locked until a human approval is audited", () => {
  const review = transitionDemoWorkflow(canonicalDemoWorkflow, {
    type: "replay-approval",
    timestamp: "2026-08-13T08:58:00+08:00",
  });

  assert.equal(review.decisionStatus, "under-review");
  assert.equal(review.workOrderStatus, "draft");

  const blocked = transitionDemoWorkflow(review, {
    type: "start-work-order",
    timestamp: "2026-08-13T08:59:00+08:00",
    actor: "海维二组",
  });
  assert.deepEqual(blocked, review);

  const approved = transitionDemoWorkflow(review, approval);
  assert.equal(approved.approval?.approver, "李明远");
  assert.equal(approved.approval?.reason, "四类审核通过");
  assert.equal(approved.workOrderStatus, "scheduled");
  assert.equal(approved.auditTrail.at(-1)?.kind, "approval");
});

test("WT-023 execution requires every task before health and knowledge feedback", () => {
  const review = transitionDemoWorkflow(canonicalDemoWorkflow, {
    type: "replay-approval",
    timestamp: "2026-08-13T08:58:00+08:00",
  });
  const approved = transitionDemoWorkflow(review, approval);
  let state = transitionDemoWorkflow(approved, {
    type: "start-work-order",
    timestamp: "2026-08-14T08:00:00+08:00",
    actor: "海维二组",
  });

  assert.equal(state.workOrderStatus, "in-progress");
  assert.equal(canCompleteFeaturedWorkOrder(state), false);

  const premature = transitionDemoWorkflow(state, {
    type: "complete-work-order",
    timestamp: "2026-08-14T09:00:00+08:00",
    actor: "林工",
  });
  assert.deepEqual(premature, state);

  for (const [index, taskId] of featuredWorkOrderTaskIds.entries()) {
    state = transitionDemoWorkflow(state, {
      type: "toggle-task",
      taskId,
      timestamp: `2026-08-14T1${index}:00:00+08:00`,
      actor: "海维二组",
    });
  }
  assert.equal(canCompleteFeaturedWorkOrder(state), true);

  const completed = transitionDemoWorkflow(state, {
    type: "complete-work-order",
    timestamp: "2026-08-14T15:20:00+08:00",
    actor: "林工",
  });

  assert.equal(completed.workOrderStatus, "completed");
  assert.equal(completed.missionStatus, "completed");
  assert.equal(completed.missionProgress, 100);
  assert.equal(completed.turbineHealthScore, 82);
  assert.equal(completed.mainBearingHealthScore, 78);
  assert.equal(completed.knowledgeCaseId, "KB-CASE-2026-WT023-CLOSED");
  assert.deepEqual(
    completed.auditTrail.slice(-2).map((event) => event.kind),
    ["verification", "knowledge"],
  );
});

test("reject, revision and escalation produce distinct audited outcomes", () => {
  const review = transitionDemoWorkflow(canonicalDemoWorkflow, {
    type: "replay-approval",
    timestamp: "2026-08-13T08:58:00+08:00",
  });

  const scenarios = [
    ["reject", "rejected", "decision-pending"],
    ["request-revision", "revision-requested", "diagnosed"],
    ["escalate", "under-review", "under-review"],
  ];

  for (const [action, decisionStatus, missionStatus] of scenarios) {
    const result = transitionDemoWorkflow(review, { ...approval, action });
    assert.equal(result.approval?.action, action);
    assert.equal(result.decisionStatus, decisionStatus);
    assert.equal(result.missionStatus, missionStatus);
    assert.equal(result.workOrderStatus, "draft");
    assert.match(result.auditTrail.at(-1)?.title ?? "", new RegExp(action));
  }
});
