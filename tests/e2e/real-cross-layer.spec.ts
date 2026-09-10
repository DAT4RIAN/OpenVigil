import { expect, test } from "@playwright/test";

const realSmoke = process.env.WINDOPS_E2E_REAL_BACKEND === "1";
const subject = process.env.WINDOPS_E2E_SUBJECT ?? "sites-release-manager";
const auditId = process.env.WINDOPS_REAL_ROTATION_AUDIT_ID ?? "real-smoke-audit";

test.describe("real Worker to FastAPI release smoke", () => {
  test.skip(
    !realSmoke,
    "Run with WINDOPS_E2E_REAL_BACKEND=1 and an isolated FastAPI/PostgreSQL backend",
  );

  test("pending rotation blocks readiness, then authorized Worker confirmation restores it", async ({
    request,
  }) => {
    const identityHeaders = {
      "oai-authenticated-user-id": subject,
      "oai-authenticated-user-email": `${subject}@example.com`,
    };
    const notReady = await request.get("/api/backend/readyz", { headers: identityHeaders });
    expect(notReady.status()).toBe(503);
    expect(await notReady.text()).toContain("CONFIGURATION_SECURITY_REMEDIATION_REQUIRED");

    const confirmed = await request.post(
      `/api/backend/platform/configuration-security-audits/${auditId}/rotation-confirmation`,
      {
        headers: {
          ...identityHeaders,
          "Idempotency-Key": "real-worker-rotation-confirm-001",
        },
        data: {
          replacement_secret_reference: "vault://windops/platform/real-smoke-rotated",
          rotation_evidence: "CHG-REAL-WORKER-ROTATION-001",
        },
      },
    );
    expect(confirmed.status()).toBe(200);
    expect(await confirmed.text()).toContain('"rotation_required":false');

    const ready = await request.get("/api/backend/readyz", { headers: identityHeaders });
    expect(ready.status()).toBe(200);
    expect(await ready.text()).toContain('"status":"ready"');
  });
});
