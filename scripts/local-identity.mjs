import { randomBytes, scrypt as scryptCallback, timingSafeEqual } from "node:crypto";
import { promisify } from "node:util";
import { safeRelativeReturnPath } from "../lib/auth-paths.ts";

const scrypt = promisify(scryptCallback);
const token = () => randomBytes(32).toString("hex");
const escape = (s) => s.replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;");
const cookieName = "__Host-openvigil-local";

export async function passwordRecord(password) {
  const salt = randomBytes(32).toString("hex");
  return { salt, hash: (await scrypt(password, salt, 64)).toString("hex") };
}

/** Authenticates local passwords only. Roles and asset grants stay in the API. */
export function localIdentity({ origin, users, now = Date.now, sessionSeconds = 3600 }) {
  const url = new URL(origin);
  if (url.protocol !== "https:" || url.hostname !== "127.0.0.1" || url.origin !== origin) {
    throw new Error("Local identity requires an HTTPS loopback origin");
  }
  if (!Number.isInteger(sessionSeconds) || sessionSeconds < 1 || sessionSeconds > 3600) {
    throw new Error("Invalid local session duration");
  }
  if (
    !Array.isArray(users) ||
    !users.length ||
    users.length > 32 ||
    new Set(users.map((u) => u.username)).size !== users.length ||
    new Set(users.map((u) => u.subject)).size !== users.length ||
    users.some(
      (u) =>
        !/^[a-z][a-z0-9-]{2,63}$/.test(u.username) ||
        !/^local-[a-z0-9-]{3,80}$/.test(u.subject) ||
        !/^[0-9a-f]{64}$/.test(u.salt) ||
        !/^[0-9a-f]{128}$/.test(u.hash),
    )
  ) {
    throw new Error("Invalid local identity records");
  }
  const accounts = new Map(users.map((u) => [u.username, { ...u }]));
  const sessions = new Map();
  const attempts = new Map();
  const recent = [];
  let activeLogins = 0;
  const cookie = (value, seconds) =>
    `${cookieName}=${value}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${seconds}`;
  const html = (title, form, status = 200, setCookie) =>
    new Response(
      `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title} · OpenVigil</title><style>body{font:16px/1.6 system-ui;margin:0;background:#f3f6f8;color:#16232b;min-height:100vh;display:grid;place-items:center}main{box-sizing:border-box;width:min(440px,90vw);padding:32px;border:1px solid #d8e0e5;border-radius:16px;background:white}label{display:block;margin:14px 0}input,button{box-sizing:border-box;width:100%;padding:12px;border:1px solid #a7b8bd;border-radius:8px;font:inherit}button{background:#087a6b;color:white;cursor:pointer}small{color:#52666d}</style><main><strong>OpenVigil · 本机验收</strong><h1>${title}</h1>${form}<p><small>此账号仅用于本机隔离环境。</small></p></main></html>`,
      {
        status,
        headers: {
          "content-type": "text/html; charset=utf-8",
          "cache-control": "no-store",
          "content-security-policy":
            "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
          "x-content-type-options": "nosniff",
          "referrer-policy": "same-origin",
          ...(setCookie ? { "set-cookie": setCookie } : {}),
        },
      },
    );
  const fail = (status, message) => html(message, '<a href="/login">返回登录</a>', status);
  const redirect = (path, setCookie) =>
    new Response(null, {
      status: 303,
      headers: {
        location: path,
        "cache-control": "no-store",
        ...(setCookie ? { "set-cookie": setCookie } : {}),
      },
    });
  return async function authenticate(request) {
    for (const [id, value] of sessions) if (value.expires <= now()) sessions.delete(id);
    for (const [name, value] of attempts) if (value.until <= now()) attempts.delete(name);
    while (recent.length && recent[0] <= now() - 60_000) recent.shift();
    const target = new URL(request.url);
    if (target.origin !== origin || request.headers.get("host") !== url.host) {
      return { response: fail(400, "无效的本机地址") };
    }
    const unsafe = !["GET", "HEAD", "OPTIONS"].includes(request.method);
    if (unsafe && request.headers.get("origin") !== origin) {
      return { response: fail(403, "请求来源校验失败") };
    }
    const cookies = (request.headers.get("cookie") ?? "").split(";").map((x) => x.trim());
    const supplied = cookies.filter((x) => x.startsWith(`${cookieName}=`));
    const id = supplied.length === 1 ? supplied[0].slice(cookieName.length + 1) : "";
    let session = sessions.get(id);
    const authPath = ["/login", "/signin-with-chatgpt", "/signout-with-chatgpt"].includes(
      target.pathname,
    );
    if (authPath && !["GET", "POST"].includes(request.method))
      return { response: fail(405, "请求方法不支持") };
    if (authPath && request.method === "GET") {
      const logout = target.pathname === "/signout-with-chatgpt";
      if (logout && !session?.subject) return { response: redirect("/login") };
      if (!logout && session?.subject)
        return {
          response: redirect(safeRelativeReturnPath(target.searchParams.get("return_to") ?? "/")),
        };
      if (!session) {
        if (sessions.size >= 1000) return { response: fail(429, "会话数量超限") };
        session = { csrf: token(), expires: now() + 300_000 };
      }
      const freshId = id && sessions.has(id) ? id : token();
      sessions.set(freshId, session);
      const path = logout ? "/signout-with-chatgpt" : "/login";
      const form = `<form method="post" action="${path}"><input type="hidden" name="csrf" value="${session.csrf}"><input type="hidden" name="return_to" value="${escape(safeRelativeReturnPath(target.searchParams.get("return_to") ?? "/"))}">${logout ? "" : '<label>账号<input name="username" autocomplete="username" required maxlength="64"></label><label>密码<input type="password" name="password" autocomplete="current-password" required maxlength="256"></label>'}<button>${logout ? "确认退出" : "登录"}</button></form>`;
      return {
        response: html(
          logout ? "退出本机账号" : "登录本机账号",
          form,
          200,
          cookie(freshId, Math.max(1, Math.floor((session.expires - now()) / 1000))),
        ),
      };
    }
    if (authPath && request.method === "POST") {
      if (
        !(request.headers.get("content-type") ?? "").startsWith("application/x-www-form-urlencoded")
      )
        return { response: fail(415, "表单格式不支持") };
      const body = await request.text();
      if (body.length > 4096) return { response: fail(413, "表单过大") };
      const fields = new URLSearchParams(body);
      if (!session || fields.get("csrf") !== session.csrf)
        return { response: fail(403, "会话校验失败，请重新登录") };
      if (target.pathname === "/signout-with-chatgpt") {
        sessions.delete(id);
        return { response: redirect("/login", cookie("", 0)) };
      }
      const username = fields.get("username") ?? "";
      const password = fields.get("password") ?? "";
      if (recent.length >= 30 || activeLogins >= 2 || (attempts.get(username)?.count ?? 0) >= 5)
        return { response: fail(429, "登录尝试过多，请稍后重试") };
      recent.push(now());
      const account = accounts.get(username);
      if (account)
        attempts.set(username, {
          count: (attempts.get(username)?.count ?? 0) + 1,
          until: now() + 600_000,
        });
      activeLogins++;
      let valid = false;
      try {
        const fallback = users[0];
        const actual = await scrypt(password.slice(0, 256), account?.salt ?? fallback.salt, 64);
        valid =
          Boolean(account) &&
          password.length <= 256 &&
          timingSafeEqual(actual, Buffer.from(account?.hash ?? fallback.hash, "hex"));
      } finally {
        activeLogins--;
      }
      if (!valid) return { response: fail(401, "账号或密码不正确") };
      if (sessions.get(id) !== session) return { response: fail(403, "登录会话已失效") };
      attempts.delete(username);
      sessions.delete(id);
      const nextId = token();
      sessions.set(nextId, {
        subject: account.subject,
        csrf: token(),
        expires: now() + sessionSeconds * 1000,
      });
      return {
        response: redirect(
          safeRelativeReturnPath(fields.get("return_to") ?? "/"),
          cookie(nextId, sessionSeconds),
        ),
      };
    }
    const headers = new Headers(request.headers);
    for (const name of [...headers.keys()]) {
      if (
        /^(oai-|x-windops-|x-forwarded-|x-e2e-)/i.test(name) ||
        ["authorization", "cookie", "forwarded"].includes(name)
      )
        headers.delete(name);
    }
    if (session?.subject) {
      headers.set("oai-authenticated-user-id", session.subject);
      headers.set("oai-authenticated-user-email", `${session.subject}@local.openvigil.invalid`);
      headers.set(
        "oai-authenticated-user-full-name",
        encodeURIComponent(`${session.subject}（本机验收）`),
      );
      headers.set("oai-authenticated-user-full-name-encoding", "percent-encoded-utf-8");
    }
    return { request: new Request(request, { headers }) };
  };
}
