/** Explicit deployment-owned origins for browser uploads using backend-signed grants. */
export function artifactUploadConnectSources(
  configured: string | undefined,
  requestUrl: string,
): string {
  if (!configured?.trim()) return "'self'";
  const values = configured.split(",").map((value) => value.trim());
  if (values.length > 10) throw new Error("Too many artifact upload origins");
  const page = new URL(requestUrl);
  const origins = values.map((value) => {
    const url = new URL(value);
    const localHttp =
      page.protocol === "http:" &&
      page.hostname === "127.0.0.1" &&
      url.protocol === "http:" &&
      url.hostname === "127.0.0.1";
    if (
      (url.protocol !== "https:" && !localHttp) ||
      url.username ||
      url.password ||
      url.search ||
      url.hash ||
      url.pathname !== "/" ||
      url.hostname.includes("*") ||
      /[\s;'"\\]/.test(value)
    )
      throw new Error("Artifact uploads require explicit HTTPS origins");
    return url.origin;
  });
  return ["'self'", ...new Set(origins)].join(" ");
}
