import type { OpenVigilRuntimeMode } from "@/lib/production-runtime";

function pathnameOf(path: string): string {
  return path.split(/[?#]/, 1)[0] || "/";
}

export function navigationOwnerPath(
  activePath: string | undefined,
  runtimeMode: OpenVigilRuntimeMode,
): string | undefined {
  if (!activePath) return undefined;
  const pathname = pathnameOf(activePath);
  if (/^\/missions\/[^/]+$/.test(pathname)) return "/missions";
  if (/^\/turbines\/[^/]+$/.test(pathname)) {
    return runtimeMode === "production" ? "/wind-farms" : "/turbines/WT-023";
  }
  return pathname;
}

export function isNavigationItemActive(
  activePath: string | undefined,
  itemHref: string,
  runtimeMode: OpenVigilRuntimeMode,
): boolean {
  return navigationOwnerPath(activePath, runtimeMode) === itemHref;
}
