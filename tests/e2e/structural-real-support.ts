import { createHash, randomUUID } from "node:crypto";
import { expect, type APIRequestContext } from "@playwright/test";

export const structuralApi = "/api/backend/";
export const fixtureIdentity = (subject = "business-manager") => ({
  "oai-authenticated-user-id": subject,
  "oai-authenticated-user-email": `${subject}@example.com`,
});

export async function structuralCommand<T>(
  request: APIRequestContext,
  path: string,
  data: unknown,
  { subject = "business-manager", status = 201, key = randomUUID() } = {},
): Promise<T> {
  const response = await request.post(structuralApi + path, {
    headers: { ...fixtureIdentity(subject), "Idempotency-Key": key },
    data,
  });
  expect(response.status(), await response.text()).toBe(status);
  return response.json() as Promise<T>;
}

// An unavailable audit sink is an explicit denial, never a successful read.
// Retain every denial, then require a real successful read within four attempts.
export async function structuralRead<T>(
  request: APIRequestContext,
  path: string,
  auditRejections: string[],
  subject = "business-manager",
): Promise<T> {
  for (let attempt = 0; attempt < 4; attempt++) {
    const response = await request.get(structuralApi + path, {
      headers: fixtureIdentity(subject),
    });
    if (response.status() === 503) {
      const body = await response.json();
      expect(Object.keys(body)).toEqual(["error"]);
      expect(body.error.code).toBe("READ_AUDIT_UNAVAILABLE");
      auditRejections.push(structuralApi + path);
      continue;
    }
    expect(response.status(), await response.text()).toBe(200);
    return response.json() as Promise<T>;
  }
  throw new Error(`Read audit admission did not recover for ${path}`);
}

export async function structuralUpload(
  request: APIRequestContext,
  path: string,
  content: Buffer,
  metadata: Record<string, unknown>,
  subject = "business-manager",
) {
  const artifactSha = createHash("sha256").update(content).digest("hex");
  const presign = await structuralCommand<{
    upload_url: string;
    artifact_uri: string;
    required_headers: Record<string, string>;
  }>(request, path, { ...metadata, artifact_sha256: artifactSha }, { subject, status: 200 });
  const put = await request.put(presign.upload_url, {
    data: content,
    headers: presign.required_headers,
  });
  expect(put.status()).toBe(200);
  return { artifact_uri: presign.artifact_uri, artifact_sha256: artifactSha };
}
