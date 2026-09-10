export const PRODUCTION_EVENT_STREAM_PATH = "/api/agent-events";
export const PRODUCTION_EVENT_RETRY_MIN_MS = 1_000;
export const PRODUCTION_EVENT_RETRY_MAX_MS = 30_000;

export type ProductionEventCursor = string;

export interface ProductionDomainEvent {
  readonly sequence: ProductionEventCursor;
  readonly event_id: string;
  readonly event_type: string;
  readonly aggregate_type: string;
  readonly aggregate_id: string;
  readonly payload: Readonly<Record<string, unknown>>;
  readonly occurred_at: string;
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export function parseProductionEventCursor(value: string | null): ProductionEventCursor | null {
  if (!value) return null;
  if (/^\d+$/.test(value)) {
    const parsed = Number(value);
    return Number.isSafeInteger(parsed) && parsed >= 0 ? value : null;
  }
  return /^v[1-9]\d*\.[A-Za-z0-9_-]{32,192}$/.test(value) ? value : null;
}

export function productionEventStreamUrl(
  eventTypes: readonly string[],
  cursor: ProductionEventCursor | null,
): string {
  const normalized = [...new Set(eventTypes)].sort();
  if (
    normalized.length === 0 ||
    normalized.some((eventType) => !/^[a-z][a-z0-9_.-]{2,95}$/.test(eventType))
  ) {
    throw new Error("Production event subscriptions require valid explicit event types.");
  }
  const parameters = new URLSearchParams();
  if (cursor === null) parameters.set("start", "latest");
  else parameters.set("cursor", cursor);
  for (const eventType of normalized) parameters.append("event_type", eventType);
  return `${PRODUCTION_EVENT_STREAM_PATH}?${parameters}`;
}

export function parseProductionDomainEvent(
  raw: string,
  expectedEventType: string,
  lastEventId: string,
): ProductionDomainEvent | null {
  let candidate: unknown;
  try {
    candidate = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isRecord(candidate) || !isRecord(candidate.payload)) return null;
  const sequence = parseProductionEventCursor(
    typeof candidate.sequence === "number"
      ? String(candidate.sequence)
      : typeof candidate.sequence === "string"
        ? candidate.sequence
        : null,
  );
  if (
    sequence === null ||
    candidate.event_type !== expectedEventType ||
    typeof candidate.event_id !== "string" ||
    !candidate.event_id ||
    typeof candidate.aggregate_type !== "string" ||
    !candidate.aggregate_type ||
    typeof candidate.aggregate_id !== "string" ||
    !candidate.aggregate_id ||
    typeof candidate.occurred_at !== "string" ||
    !candidate.occurred_at
  ) {
    return null;
  }
  const cursor = parseProductionEventCursor(lastEventId);
  if (cursor !== null && cursor !== sequence) return null;
  return { ...candidate, sequence } as unknown as ProductionDomainEvent;
}

export function parseProductionControlCursor(
  raw: string,
  lastEventId: string,
): ProductionEventCursor | null {
  let candidate: unknown;
  try {
    candidate = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isRecord(candidate)) return null;
  const cursor = parseProductionEventCursor(
    typeof candidate.next_cursor === "number"
      ? String(candidate.next_cursor)
      : typeof candidate.next_cursor === "string"
        ? candidate.next_cursor
        : null,
  );
  if (cursor === null) return null;
  const eventCursor = parseProductionEventCursor(lastEventId);
  return eventCursor === null || eventCursor === cursor ? cursor : null;
}
