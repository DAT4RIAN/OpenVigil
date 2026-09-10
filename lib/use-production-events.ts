"use client";

import { useEffect, useRef, useState } from "react";

import {
  parseProductionControlCursor,
  parseProductionDomainEvent,
  parseProductionEventCursor,
  productionEventStreamUrl,
  PRODUCTION_EVENT_RETRY_MAX_MS,
  PRODUCTION_EVENT_RETRY_MIN_MS,
  type ProductionDomainEvent,
  type ProductionEventCursor,
} from "./production-events";

export type ProductionEventStatus = "idle" | "connecting" | "connected" | "reconnecting";

interface ProductionEventOptions {
  readonly enabled: boolean;
  readonly eventTypes: readonly string[];
  readonly cursorKey: string;
  readonly onEvent?: (event: ProductionDomainEvent) => void;
  readonly onReady?: () => void;
  readonly minimumDispatchIntervalMs?: number;
}

function storedCursor(key: string): ProductionEventCursor | null {
  try {
    return parseProductionEventCursor(window.sessionStorage.getItem(key));
  } catch {
    return null;
  }
}

function storeCursor(key: string, cursor: ProductionEventCursor): void {
  try {
    window.sessionStorage.setItem(key, String(cursor));
  } catch {
    // A blocked sessionStorage must not disable the authenticated event stream.
  }
}

export function useProductionEvents({
  enabled,
  eventTypes,
  cursorKey,
  onEvent,
  onReady,
  minimumDispatchIntervalMs = 500,
}: ProductionEventOptions) {
  const [status, setStatus] = useState<ProductionEventStatus>(enabled ? "connecting" : "idle");
  const [cursor, setCursor] = useState<ProductionEventCursor | null>(null);
  const [lastEvent, setLastEvent] = useState<ProductionDomainEvent | null>(null);
  const onEventRef = useRef(onEvent);
  const onReadyRef = useRef(onReady);
  const eventTypeKey = [...new Set(eventTypes)].sort().join("\u001f");

  useEffect(() => {
    onEventRef.current = onEvent;
    onReadyRef.current = onReady;
  }, [onEvent, onReady]);

  useEffect(() => {
    if (!enabled) return;

    const subscribedTypes = eventTypeKey.split("\u001f").filter(Boolean);
    let lastCursor = storedCursor(cursorKey);
    let source: EventSource | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let dispatchTimer: ReturnType<typeof setTimeout> | undefined;
    let pendingEvent: ProductionDomainEvent | null = null;
    let lastDispatchAt = 0;
    let retryDelay = PRODUCTION_EVENT_RETRY_MIN_MS;
    let disposed = false;

    const persistCursor = (nextCursor: ProductionEventCursor) => {
      lastCursor = nextCursor;
      setCursor(nextCursor);
      storeCursor(cursorKey, nextCursor);
    };
    const dispatch = (event: ProductionDomainEvent) => {
      setLastEvent(event);
      const elapsed = Date.now() - lastDispatchAt;
      if (elapsed >= minimumDispatchIntervalMs && dispatchTimer === undefined) {
        lastDispatchAt = Date.now();
        onEventRef.current?.(event);
        return;
      }
      pendingEvent = event;
      if (dispatchTimer !== undefined) return;
      dispatchTimer = setTimeout(
        () => {
          dispatchTimer = undefined;
          if (!pendingEvent || disposed) return;
          const queued = pendingEvent;
          pendingEvent = null;
          lastDispatchAt = Date.now();
          onEventRef.current?.(queued);
        },
        Math.max(0, minimumDispatchIntervalMs - elapsed),
      );
    };
    const schedule = (delay: number) => {
      if (disposed || retryTimer !== undefined) return;
      retryTimer = setTimeout(() => {
        retryTimer = undefined;
        connect();
      }, delay);
    };
    const connect = () => {
      if (disposed) return;
      setStatus(lastCursor === null ? "connecting" : "reconnecting");
      const startsAtLatest = lastCursor === null;
      source = new EventSource(productionEventStreamUrl(subscribedTypes, lastCursor), {
        withCredentials: true,
      });
      source.addEventListener("open", () => {
        retryDelay = PRODUCTION_EVENT_RETRY_MIN_MS;
        setStatus("connected");
      });
      source.addEventListener("stream.ready", (rawEvent) => {
        const event = rawEvent as MessageEvent<string>;
        const readyCursor = parseProductionControlCursor(event.data, event.lastEventId);
        if (readyCursor === null) return;
        // The authoritative stream may reset a stale browser cursor after a
        // database restore or a controlled backend replacement.
        persistCursor(readyCursor);
        if (startsAtLatest) onReadyRef.current?.();
      });
      for (const eventType of subscribedTypes) {
        source.addEventListener(eventType, (rawEvent) => {
          const event = rawEvent as MessageEvent<string>;
          const parsed = parseProductionDomainEvent(event.data, eventType, event.lastEventId);
          if (!parsed || parsed.sequence === lastCursor) return;
          persistCursor(parsed.sequence);
          dispatch(parsed);
        });
      }
      source.addEventListener("reconnect", (rawEvent) => {
        const event = rawEvent as MessageEvent<string>;
        const reconnectCursor = parseProductionControlCursor(event.data, event.lastEventId);
        if (reconnectCursor !== null) persistCursor(reconnectCursor);
        source?.close();
        source = null;
        setStatus("reconnecting");
        schedule(0);
      });
      source.addEventListener("error", () => {
        source?.close();
        source = null;
        setStatus("reconnecting");
        schedule(retryDelay);
        retryDelay = Math.min(PRODUCTION_EVENT_RETRY_MAX_MS, retryDelay * 2);
      });
    };

    const startTimer = setTimeout(() => {
      setCursor(lastCursor);
      connect();
    }, 0);
    return () => {
      disposed = true;
      clearTimeout(startTimer);
      if (retryTimer !== undefined) clearTimeout(retryTimer);
      if (dispatchTimer !== undefined) clearTimeout(dispatchTimer);
      source?.close();
    };
  }, [cursorKey, enabled, eventTypeKey, minimumDispatchIntervalMs]);

  return { status: enabled ? status : "idle", cursor, lastEvent } as const;
}
