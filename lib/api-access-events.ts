export const API_ACCESS_EVENT = "windops-api-access-failure";

export interface ApiAccessFailure {
  readonly kind: "authentication" | "authorization" | "backend" | "network";
  readonly status: number | null;
  readonly code: string;
  readonly message: string;
}

export function publishApiAccessFailure(failure: ApiAccessFailure): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(API_ACCESS_EVENT, { detail: failure }));
}
