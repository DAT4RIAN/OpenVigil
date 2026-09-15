import assert from "node:assert/strict";
import test from "node:test";

import {
  chatGPTSignInPath,
  chatGPTSignOutPath,
  loginPath,
  safeRelativeReturnPath,
} from "../lib/auth-paths.ts";
import {
  decodeTrustedSession,
  encodeTrustedSession,
  parseBackendIdentitySession,
} from "../lib/identity-session.ts";

const fieldSession = {
  subject: "sites-user-42",
  email: "field@example.com",
  roles: ["field_technician"],
  capabilities: ["mission.comment", "view.missions", "work_order.task.complete"],
  scope: {
    tenant_count: 1,
    wind_farm_count: 1,
    turbine_count: 2,
    entity_count: 0,
    allow_global: false,
  },
};

test("trusted session round trip preserves only the validated backend contract", () => {
  const parsed = parseBackendIdentitySession(fieldSession, "sites-user-42");
  assert.deepEqual(parsed, fieldSession);

  const encoded = encodeTrustedSession(parsed);
  assert.deepEqual(decodeTrustedSession(encoded, "sites-user-42"), fieldSession);
  assert.equal(decodeTrustedSession(encoded, "different-user"), null);
});

test("trusted session decoding fails closed on forged capability and malformed scope", () => {
  assert.equal(
    parseBackendIdentitySession(
      { ...fieldSession, capabilities: [...fieldSession.capabilities, "platform.manage.evil"] },
      fieldSession.subject,
    ),
    null,
  );
  assert.equal(
    parseBackendIdentitySession(
      { ...fieldSession, scope: { ...fieldSession.scope, turbine_count: -1 } },
      fieldSession.subject,
    ),
    null,
  );
  assert.equal(decodeTrustedSession("forged-manager-session", fieldSession.subject), null);
  assert.equal(decodeTrustedSession("a".repeat(8193), fieldSession.subject), null);
});

test("ChatGPT auth paths preserve safe local returns and reject redirects or auth loops", () => {
  assert.equal(
    chatGPTSignInPath("/missions?status=open#review"),
    "/signin-with-chatgpt?return_to=%2Fmissions%3Fstatus%3Dopen%23review",
  );
  assert.equal(
    chatGPTSignInPath("https://evil.example/steal"),
    "/signin-with-chatgpt?return_to=%2F",
  );
  assert.equal(chatGPTSignInPath("//evil.example/steal"), "/signin-with-chatgpt?return_to=%2F");
  assert.equal(chatGPTSignOutPath("/signout-with-chatgpt"), "/signout-with-chatgpt?return_to=%2F");
});

test("login return destinations reject external URLs, control characters and authentication loops", () => {
  assert.equal(
    loginPath("/missions?status=open#review"),
    "/login?return_to=%2Fmissions%3Fstatus%3Dopen%23review",
  );
  for (const unsafe of [
    "https://evil.example",
    "//evil.example",
    "/\\evil.example",
    "/\nevil.example",
    "/login",
    "/login/?return_to=/login",
    "/%6cogin",
    "/callback",
    "/signin-with-chatgpt/",
    "/signout-with-chatgpt",
    "/%zz",
  ]) {
    assert.equal(safeRelativeReturnPath(unsafe), "/", unsafe);
  }
  assert.equal(
    safeRelativeReturnPath("/missions?status=open#review"),
    "/missions?status=open#review",
  );
});
