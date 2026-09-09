import { activityEvents, alarms } from "./operations-data";
import { scadaSeries } from "./telemetry-data";
import { windFarm } from "./farm-data";
import {
  realtimeAgentActivityData,
  realtimeAlarmData,
  selectRealtimeAlarm,
} from "./realtime-workflow-overlay";
import type { ServerWorkflowSnapshot } from "./server-workflow-contract";

export const REALTIME_CHANNELS = ["scada", "alarms", "agent-events"] as const;
export type RealtimeChannel = (typeof REALTIME_CHANNELS)[number];

export interface RealtimeFrame {
  readonly protocol: "windops.realtime.v1";
  readonly channel: RealtimeChannel;
  readonly event: "scada-update" | "alarm-update" | "agent-activity";
  readonly sequence: number;
  readonly emittedAt: string;
  readonly deterministic: true;
  readonly correlationId: string;
  readonly data: Readonly<Record<string, unknown>>;
}

const realtimeEpoch = new Date(windFarm.lastUpdatedAt).getTime();
const scadaMetrics = [
  "main-bearing-vibration-rms",
  "main-bearing-temperature",
  "active-power",
  "anomaly-score",
] as const;

const normalizedSequence = (sequence: number): number =>
  Number.isInteger(sequence) && sequence >= 0 ? sequence : 0;

const emittedAtFor = (sequence: number): string =>
  new Date(realtimeEpoch + sequence * 15_000).toISOString();

/**
 * Produce one repeatable public event frame for WebSocket delivery and tests.
 * Frames contain only observable domain facts; no hidden model reasoning is exposed.
 */
export function buildRealtimeFrame(
  channel: RealtimeChannel,
  sequence: number,
  workflow?: ServerWorkflowSnapshot,
  alarmItems: readonly (typeof alarms)[number][] = alarms,
): RealtimeFrame {
  const normalized = normalizedSequence(sequence);
  const emittedAt = emittedAtFor(normalized);

  if (channel === "scada") {
    const values = scadaMetrics.map((metric) => {
      const series = scadaSeries.find((candidate) => candidate.metric === metric)!;
      const windowStart = Math.max(0, series.points.length - 12);
      const point =
        series.points[windowStart + (normalized % (series.points.length - windowStart))]!;
      return Object.freeze({
        seriesId: series.id,
        turbineId: series.turbineId,
        metric: series.metric,
        label: series.label,
        value: point.value,
        unit: series.unit,
        quality: point.quality,
        isAnomaly: point.isAnomaly,
      });
    });

    return Object.freeze({
      protocol: "windops.realtime.v1" as const,
      channel,
      event: "scada-update" as const,
      sequence: normalized,
      emittedAt,
      deterministic: true as const,
      correlationId: `RT-SCADA-WT023-${String(normalized).padStart(6, "0")}`,
      data: Object.freeze({ turbineId: "WT-023", values: Object.freeze(values) }),
    });
  }

  if (channel === "alarms") {
    const alarm = selectRealtimeAlarm(alarmItems, normalized, workflow);
    return Object.freeze({
      protocol: "windops.realtime.v1" as const,
      channel,
      event: "alarm-update" as const,
      sequence: normalized,
      emittedAt,
      deterministic: true as const,
      correlationId: `RT-${alarm.id}-${String(normalized).padStart(6, "0")}`,
      data: realtimeAlarmData(alarm),
    });
  }

  const activity = activityEvents[normalized % activityEvents.length]!;
  return Object.freeze({
    protocol: "windops.realtime.v1" as const,
    channel,
    event: "agent-activity" as const,
    sequence: normalized,
    emittedAt,
    deterministic: true as const,
    correlationId: `RT-${activity.id}-${String(normalized).padStart(6, "0")}`,
    data: realtimeAgentActivityData(activity, normalized, workflow),
  });
}

export const realtimeHello = (channel: RealtimeChannel) =>
  Object.freeze({
    protocol: "windops.realtime.v1" as const,
    channel,
    event: "hello" as const,
    sequence: -1,
    emittedAt: windFarm.lastUpdatedAt,
    snapshotAt: windFarm.lastUpdatedAt,
    deterministic: true as const,
    cadenceMs: channel === "scada" ? 1_000 : 2_000,
  });
