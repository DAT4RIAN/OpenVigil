import assert from "node:assert/strict";
import test from "node:test";

import {
  collectionResponse,
  errorResponse,
  isNonEmptyString,
  isRecord,
  jsonResponse,
  parseBoundedInteger,
} from "../app/api/_shared.ts";

test("shared JSON responses preserve no-store headers and status", async () => {
  const response = jsonResponse({ ok: true }, 202);

  assert.equal(response.status, 202);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.equal(response.headers.get("content-type"), "application/json; charset=utf-8");
  assert.deepEqual(await response.json(), { ok: true });
});

test("shared collection and error envelopes preserve their wire contracts", async () => {
  const collection = collectionResponse(["first", "second"], { total: 9, cursor: "next" });
  assert.deepEqual(await collection.json(), {
    data: ["first", "second"],
    meta: { count: 2, total: 9, cursor: "next" },
  });

  const error = errorResponse("INVALID_INPUT", "Input is invalid.", 422);
  assert.equal(error.status, 422);
  assert.deepEqual(await error.json(), {
    error: { code: "INVALID_INPUT", message: "Input is invalid." },
  });
});

test("shared input guards reject arrays, blank strings, and non-decimal integers", () => {
  assert.equal(isRecord({ value: 1 }), true);
  assert.equal(isRecord([]), false);
  assert.equal(isRecord(null), false);
  assert.equal(isNonEmptyString(" value "), true);
  assert.equal(isNonEmptyString("  "), false);
  assert.equal(isNonEmptyString(1), false);

  assert.equal(parseBoundedInteger(null, 7, 1, 10), 7);
  assert.equal(parseBoundedInteger("01", 7, 1, 10), 1);
  assert.equal(parseBoundedInteger("10", 7, 1, 10), 10);
  for (const value of ["", " ", "-1", "+1", "1.0", "11", "9007199254740992"]) {
    assert.equal(parseBoundedInteger(value, 7, 1, 10), null);
  }
});
