import assert from "node:assert/strict";
import test from "node:test";

import { turbines } from "../lib/farm-data.ts";
import { buildGenericSubsystemAssessments } from "../lib/generic-subsystem-data.ts";

test("every turbine receives twelve deterministic subsystem assessments", () => {
  const requiredSubsystems = [
    "叶片",
    "轮毂",
    "主轴",
    "主轴承",
    "齿轮箱",
    "发电机",
    "变流器",
    "偏航系统",
    "变桨系统",
    "塔架",
    "基础",
    "电气系统",
  ];
  for (const turbine of turbines) {
    const first = buildGenericSubsystemAssessments(turbine);
    const repeated = buildGenericSubsystemAssessments(turbine);

    assert.deepEqual(repeated, first);
    assert.equal(first.length, 12);
    assert.equal(new Set(first.map((item) => item.key)).size, 12);
    assert.deepEqual([...first.map((item) => item.name)].sort(), [...requiredSubsystems].sort());
    assert.equal(
      first.reduce((total, assessment) => total + assessment.alertCount, 0),
      turbine.activeAlarmCount,
      `${turbine.id} subsystem alarms must reconcile with the asset total`,
    );
    if (turbine.activeAlarmCount === 0) {
      assert.ok(
        first.every((assessment) => assessment.alertCount === 0),
        `${turbine.id} cannot invent subsystem alarms`,
      );
    }
    for (const assessment of first) {
      assert.ok(assessment.healthScore >= 42 && assessment.healthScore <= 99);
      assert.ok(assessment.alertCount >= 0);
      assert.deepEqual(Object.keys(assessment).sort(), [
        "alertCount",
        "healthScore",
        "key",
        "name",
        "state",
      ]);
    }
  }
});

test("offline turbines propagate an offline subsystem state", () => {
  const offlineTurbine = turbines.find(
    (turbine) => turbine.status === "offline" || turbine.status === "communication-lost",
  );
  assert.ok(offlineTurbine);

  const assessments = buildGenericSubsystemAssessments(offlineTurbine);
  assert.ok(assessments.every((assessment) => assessment.state === "offline"));
});
