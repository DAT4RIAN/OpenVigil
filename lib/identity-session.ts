export const OPENVIGIL_CAPABILITIES = [
  "agent.manage",
  "alarm.command",
  "mission.approve",
  "mission.comment",
  "mission.create",
  "mission.escalate",
  "mission.reject",
  "mission.request_revision",
  "model.manage",
  "platform.manage",
  "report.generate",
  "resource.manage",
  "view.agents",
  "view.alarms",
  "view.assets",
  "view.dashboard",
  "view.decisions",
  "view.knowledge",
  "view.missions",
  "view.models",
  "view.platform",
  "view.reports",
  "view.resources",
  "view.telemetry",
  "view.work_orders",
  "work_order.schedule",
  "work_order.task.complete",
] as const;

export type OpenVigilCapability = (typeof OPENVIGIL_CAPABILITIES)[number];

export interface BackendIdentitySession {
  readonly subject: string;
  readonly email: string | null;
  readonly roles: readonly string[];
  readonly capabilities: readonly OpenVigilCapability[];
  readonly scope: {
    readonly tenant_count: number;
    readonly wind_farm_count: number;
    readonly turbine_count: number;
    readonly entity_count: number;
    readonly allow_global: boolean;
  };
}

export interface OpenVigilIdentitySession extends BackendIdentitySession {
  readonly displayName: string;
  readonly signOutPath: string;
}

export const TRUSTED_SESSION_HEADER = "x-windops-trusted-session";

const capabilitySet = new Set<string>(OPENVIGIL_CAPABILITIES);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function boundedStrings(value: unknown, maximum: number): string[] | null {
  if (!Array.isArray(value) || value.length > maximum) return null;
  const strings = value.filter(
    (item): item is string => typeof item === "string" && item.length > 0 && item.length <= 128,
  );
  return strings.length === value.length ? strings : null;
}

export function parseBackendIdentitySession(
  value: unknown,
  expectedSubject: string,
): BackendIdentitySession | null {
  if (!isRecord(value) || value.subject !== expectedSubject) return null;
  if (value.email !== null && typeof value.email !== "string") return null;
  const roles = boundedStrings(value.roles, 8);
  const capabilities = boundedStrings(value.capabilities, OPENVIGIL_CAPABILITIES.length);
  if (!roles || !capabilities || !capabilities.every((item) => capabilitySet.has(item))) {
    return null;
  }
  if (!isRecord(value.scope)) return null;
  const counts = [
    value.scope.tenant_count,
    value.scope.wind_farm_count,
    value.scope.turbine_count,
    value.scope.entity_count,
  ];
  if (
    counts.some((count) => !Number.isInteger(count) || Number(count) < 0) ||
    typeof value.scope.allow_global !== "boolean"
  ) {
    return null;
  }
  return {
    subject: value.subject,
    email: value.email as string | null,
    roles,
    capabilities: capabilities as OpenVigilCapability[],
    scope: {
      tenant_count: Number(value.scope.tenant_count),
      wind_farm_count: Number(value.scope.wind_farm_count),
      turbine_count: Number(value.scope.turbine_count),
      entity_count: Number(value.scope.entity_count),
      allow_global: value.scope.allow_global,
    },
  };
}

function base64Url(value: Uint8Array): string {
  let binary = "";
  for (const byte of value) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

export function encodeTrustedSession(session: BackendIdentitySession): string {
  return base64Url(new TextEncoder().encode(JSON.stringify(session)));
}

export function decodeTrustedSession(
  encoded: string | null,
  expectedSubject: string,
): BackendIdentitySession | null {
  if (!encoded || encoded.length > 8_192 || !/^[A-Za-z0-9_-]+$/.test(encoded)) return null;
  try {
    const padded = encoded
      .replaceAll("-", "+")
      .replaceAll("_", "/")
      .padEnd(Math.ceil(encoded.length / 4) * 4, "=");
    const binary = atob(padded);
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    return parseBackendIdentitySession(
      JSON.parse(new TextDecoder().decode(bytes)),
      expectedSubject,
    );
  } catch {
    return null;
  }
}
