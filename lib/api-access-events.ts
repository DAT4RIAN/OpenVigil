export const API_ACCESS_EVENT = "windops-api-access-failure";
export const API_ACCESS_RECOVERY_EVENT = "windops-api-access-recovery";

export interface ApiAccessFailure {
  readonly kind: "authentication" | "authorization" | "backend" | "network";
  readonly status: number | null;
  readonly code: string;
  readonly message: string;
  readonly scope?: string;
  readonly operationKey?: string | null;
}

export interface ApiAccessRecovery {
  readonly scope: string;
  readonly operationKey?: string | null;
}

export function publishApiAccessFailure(failure: ApiAccessFailure): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(API_ACCESS_EVENT, { detail: failure }));
}

export function publishApiAccessRecovery(recovery: ApiAccessRecovery): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(API_ACCESS_RECOVERY_EVENT, { detail: recovery }));
}
