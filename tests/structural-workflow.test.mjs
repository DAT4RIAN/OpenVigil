import assert from "node:assert/strict";
import test from "node:test";
import { decisionConfidence, decisionMoney, decisionQuantity } from "../lib/decision-values.ts";
import { structuralFact, structuralStatus } from "../lib/structural-workflow.ts";
import { isAllowedProductionGatewayRequest } from "../lib/production-runtime.ts";

test("structural workflow gateway allows only the declared read and command methods", () => {
  const paths = [
    ["/api/v1/structural-missions", "POST"],
    ["/api/v1/structural-missions/M-SYNTHETIC", "GET"],
    ["/api/v1/structural-work-orders/WO-SYNTHETIC", "GET"],
    ["/api/v1/structural-work-orders/WO-SYNTHETIC/health-review", "POST"],
    ["/api/v1/structural-work-orders/WO-SYNTHETIC/retests", "POST"],
    ["/api/v1/structural-work-orders/WO-SYNTHETIC/retests/uploads/presign", "POST"],
    ["/api/v1/structural-cases", "GET"],
    ["/api/v1/structural-cases/CASE-SYNTHETIC/review", "POST"],
  ];
  for (const [path, method] of paths) {
    assert.equal(isAllowedProductionGatewayRequest(method, path), true, path);
    for (const denied of ["GET", "POST", "PATCH", "DELETE"].filter((value) => value !== method))
      assert.equal(isAllowedProductionGatewayRequest(denied, path), false, `${denied} ${path}`);
  }
  for (const path of [
    "/api/v1/structural-missions/a",
    `/api/v1/structural-missions/${"x".repeat(41)}`,
    "/api/v1/structural-work-orders/WO-SYNTHETIC/resolve",
    "/api/v1/structural-cases/CASE-SYNTHETIC/publish",
  ])
    assert.equal(isAllowedProductionGatewayRequest("POST", path), false);
});

test("unknown structural quantities preserve absence while actual zero remains zero", () => {
  assert.equal(decisionMoney(null), "未评估");
  assert.equal(decisionMoney(0), "¥0.0 万");
  assert.equal(decisionQuantity(undefined, "h"), "未评估");
  assert.equal(decisionQuantity(0, "h"), "0 h");
  assert.equal(decisionConfidence(null), "未量化");
  assert.equal(decisionConfidence(0), "0%");
  assert.equal(structuralFact(null), "未提供");
  assert.equal(structuralFact(0), "0");
  assert.equal(structuralStatus("awaiting_health_review"), "待健康复核");
  assert.equal(structuralStatus("unknown_future_state"), "unknown_future_state");
});
