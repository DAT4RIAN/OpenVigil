"use client";

import { useEffect, useState } from "react";

import type { RealtimeChannel, RealtimeFrame } from "./realtime-stream";

export type RealtimeConnectionStatus = "idle" | "connecting" | "connected" | "fallback";

export function useRealtimeChannel(channel: RealtimeChannel, enabled = true) {
  const [status, setStatus] = useState<RealtimeConnectionStatus>(enabled ? "connecting" : "idle");
  const [frame, setFrame] = useState<RealtimeFrame | null>(null);

  useEffect(() => {
    if (!enabled) return;

    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let disposed = false;

    const connect = () => {
      if (disposed) return;
      setStatus("connecting");
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      socket = new WebSocket(`${protocol}//${window.location.host}/ws/${channel}`);
      socket.addEventListener("open", () => setStatus("connected"));
      socket.addEventListener("message", (event) => {
        try {
          const candidate = JSON.parse(String(event.data)) as Partial<RealtimeFrame>;
          if (
            candidate.protocol === "windops.realtime.v1" &&
            candidate.channel === channel &&
            typeof candidate.sequence === "number" &&
            typeof candidate.emittedAt === "string" &&
            candidate.data
          ) {
            setFrame(candidate as RealtimeFrame);
          }
        } catch {
          setStatus("fallback");
        }
      });
      socket.addEventListener("error", () => setStatus("fallback"));
      socket.addEventListener("close", () => {
        if (disposed) return;
        setStatus("fallback");
        retryTimer = setTimeout(connect, 10_000);
      });
    };

    const startTimer = setTimeout(connect, 0);
    return () => {
      disposed = true;
      clearTimeout(startTimer);
      if (retryTimer !== undefined) clearTimeout(retryTimer);
      socket?.close(1000, "component unmounted");
    };
  }, [channel, enabled]);

  return { status: enabled ? status : "idle", frame: enabled ? frame : null } as const;
}
