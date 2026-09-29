import assert from "node:assert/strict";
import test from "node:test";
import { localIdentity, passwordRecord } from "../scripts/local-identity.mjs";

const origin = "https://127.0.0.1:9443";
const record = await passwordRecord("test-only-password-unique");
const users = [{ username: "manager", subject: "local-manager", ...record }];
const request = (path, options = {}) =>
  new Request(origin + path, {
    ...options,
    headers: { host: "127.0.0.1:9443", ...options.headers },
  });
async function form(auth, path = "/login", cookie) {
  const { response } = await auth(request(path, { headers: cookie ? { cookie } : {} }));
  assert.equal(response.headers.get("referrer-policy"), "same-origin");
  const csrf = (await response.text()).match(/name="csrf" value="([a-f0-9]+)"/)[1];
  return { csrf, cookie: response.headers.get("set-cookie").split(";")[0] };
}
const submit = (auth, state, overrides = {}, path = "/login") =>
  auth(
    request(path, {
      method: "POST",
      headers: {
        origin,
        cookie: state.cookie,
        "content-type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams({
        csrf: state.csrf,
        username: "manager",
        password: "test-only-password-unique",
        ...overrides,
      }),
    }),
  );

test("real passwords rotate sessions, strip forged identity, revoke on logout and expire", async () => {
  let time = 1000;
  const auth = localIdentity({ origin, users, now: () => time });
  const state = await form(auth);
  const bad = await submit(auth, state, { password: "wrong" });
  assert.equal(bad.response.status, 401);
  const login = await submit(auth, state, { return_to: "//evil.invalid" });
  assert.equal(login.response.status, 303);
  assert.equal(login.response.headers.get("location"), "/");
  const setCookie = login.response.headers.get("set-cookie");
  assert.match(setCookie, /HttpOnly; Secure; SameSite=Strict/);
  const cookie = setCookie.split(";")[0];
  assert.notEqual(cookie, state.cookie);
  const headers = {
    cookie,
    "oai-authenticated-user-id": "attacker",
    authorization: "Bearer forged",
    "x-windops-trusted-session": "fake",
    "x-forwarded-host": "evil",
  };
  const result = await auth(request("/api/session", { headers }));
  assert.equal(result.request.headers.get("oai-authenticated-user-id"), "local-manager");
  assert.equal(
    result.request.headers.get("oai-authenticated-user-email"),
    "local-manager@local.openvigil.invalid",
  );
  for (const name of ["authorization", "cookie", "x-windops-trusted-session", "x-forwarded-host"])
    assert.equal(result.request.headers.get(name), null);
  const old = await auth(request("/", { headers: { cookie: state.cookie } }));
  assert.equal(old.request.headers.get("oai-authenticated-user-id"), null);
  const logout = await form(auth, "/signout-with-chatgpt", cookie);
  assert.equal((await submit(auth, logout, {}, "/signout-with-chatgpt")).response.status, 303);
  assert.equal(
    (await auth(request("/", { headers }))).request.headers.get("oai-authenticated-user-id"),
    null,
  );
  const again = await submit(auth, await form(auth));
  time += 3_600_001;
  const expired = await auth(
    request("/", { headers: { cookie: again.response.headers.get("set-cookie").split(";")[0] } }),
  );
  assert.equal(expired.request.headers.get("oai-authenticated-user-id"), null);
});

test("CSRF, host injection, unknown credentials and brute force fail closed", async () => {
  const auth = localIdentity({ origin, users });
  const state = await form(auth);
  assert.equal((await submit(auth, state, { csrf: "forged" })).response.status, 403);
  assert.equal(
    (await auth(request("/login", { method: "POST", headers: { origin: "https://evil.invalid" } })))
      .response.status,
    403,
  );
  assert.equal(
    (await auth(request("/", { headers: { host: "evil.invalid" } }))).response.status,
    400,
  );
  assert.equal((await submit(auth, state, { username: "unknown" })).response.status, 401);
  for (let i = 0; i < 5; i++)
    assert.equal((await submit(auth, state, { password: "bad" })).response.status, 401);
  assert.equal((await submit(auth, state)).response.status, 429);
  const forged = await auth(
    request("/api/session", {
      headers: {
        "oai-authenticated-user-id": "local-manager",
        "x-windops-user-id": "local-manager",
      },
    }),
  );
  assert.equal(forged.request.headers.get("oai-authenticated-user-id"), null);
  assert.equal(forged.request.headers.get("x-windops-user-id"), null);
});

test("concurrent password posts cannot reuse a consumed login session", async () => {
  const auth = localIdentity({ origin, users });
  const state = await form(auth);
  const result = await Promise.all([submit(auth, state), submit(auth, state)]);
  assert.deepEqual(result.map((r) => r.response.status).sort(), [303, 403]);
  assert.throws(() => localIdentity({ origin: "https://0.0.0.0:9443", users }));
  assert.throws(() => localIdentity({ origin, users: [...users, ...users] }));
});
