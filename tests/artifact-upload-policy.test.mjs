import assert from "node:assert/strict";
import test from "node:test";
import { artifactUploadConnectSources } from "../lib/artifact-upload-policy.ts";

test("upload policy defaults to self and adds only explicit unique origins", () => {
  assert.equal(artifactUploadConnectSources(undefined, "https://app.example"), "'self'");
  assert.equal(
    artifactUploadConnectSources(
      "https://objects.example,https://objects.example/",
      "https://app.example",
    ),
    "'self' https://objects.example",
  );
});

test("upload policy rejects insecure or injected sources", () => {
  for (const input of [
    "*",
    "https://*.example",
    "http://objects.example",
    "http://127.0.0.1:9000",
    "https://user:pass@objects.example",
    "https://objects.example/path",
    "https://objects.example?key=1",
    "https://objects.example#fragment",
    "https://objects.example; script-src *",
    "https://objects.example,",
    "data:",
  ]) {
    assert.throws(() => artifactUploadConnectSources(input, "https://app.example"));
  }
});

test("HTTP object storage is limited to a loopback HTTP page", () => {
  assert.equal(
    artifactUploadConnectSources("http://127.0.0.1:9000", "http://127.0.0.1:4179"),
    "'self' http://127.0.0.1:9000",
  );
  assert.throws(() =>
    artifactUploadConnectSources("http://objects.example", "http://127.0.0.1:4179"),
  );
});
