import { scadaSeries } from "./telemetry-data";
import { turbines, windFarm } from "./farm-data";
import type { ScadaSeries } from "./types";

export const SCADA_HISTORY_RANGES = ["LIVE", "1H", "6H", "24H", "7D", "30D"] as const;
export type ScadaHistoryRange = (typeof SCADA_HISTORY_RANGES)[number];

const rangeConfig: Record<
  ScadaHistoryRange,
  { readonly durationMinutes: number; readonly samples: number; readonly intervalLabel: string }
> = {
  LIVE: { durationMinutes: 11, samples: 12, intervalLabel: "1 min" },
  "1H": { durationMinutes: 60, samples: 13, intervalLabel: "5 min" },
  "6H": { durationMinutes: 360, samples: 25, intervalLabel: "15 min" },
  "24H": { durationMinutes: 1_440, samples: 97, intervalLabel: "15 min" },
  "7D": { durationMinutes: 10_080, samples: 169, intervalLabel: "1 hour" },
  "30D": { durationMinutes: 43_200, samples: 181, intervalLabel: "4 hours" },
};

export interface ScadaHistorySnapshot {
  readonly data: readonly ScadaSeries[];
  readonly meta: {
    readonly count: number;
    readonly pointCount: number;
    readonly turbineId: string;
    readonly range: ScadaHistoryRange;
    readonly interval: string;
    readonly startsAt: string;
    readonly endsAt: string;
    readonly snapshotAt: string;
    readonly deterministic: true;
  };
}

export function getScadaHistory(
  range: ScadaHistoryRange = "24H",
  turbineId = "WT-023",
): ScadaHistorySnapshot {
  const normalizedTurbineId = turbineId.trim().toUpperCase();
  const config = rangeConfig[range];
  const snapshotMs = new Date(windFarm.lastUpdatedAt).getTime();
  const startMs = snapshotMs - config.durationMinutes * 60_000;
  const turbine = turbines.find((candidate) => candidate.id === normalizedTurbineId);
  const turbineOrdinal = Number(normalizedTurbineId.slice(3));
  const valueFactor = 1 + ((turbineOrdinal - 23) % 7) * 0.006;
  const sourceSeries = turbine
    ? scadaSeries.map((series) =>
        normalizedTurbineId === "WT-023"
          ? series
          : {
              ...series,
              turbineId: normalizedTurbineId,
              currentValue: Number((series.currentValue * valueFactor).toFixed(3)),
              points: series.points.map((point) => ({
                ...point,
                value: Number((point.value * valueFactor).toFixed(3)),
              })),
            },
      )
    : [];

  const data = Object.freeze(
    sourceSeries.map((series) => {
      const points = Object.freeze(
        Array.from({ length: config.samples }, (_, index) => {
          const ratio = config.samples === 1 ? 1 : index / (config.samples - 1);
          const sourceIndex = Math.round(ratio * (series.points.length - 1));
          const source = series.points[sourceIndex]!;
          const timestamp = new Date(
            startMs + ratio * config.durationMinutes * 60_000,
          ).toISOString();
          return Object.freeze({ ...source, timestamp });
        }),
      );
      return Object.freeze({ ...series, points });
    }),
  );

  return Object.freeze({
    data,
    meta: Object.freeze({
      count: data.length,
      pointCount: data.reduce((total, series) => total + series.points.length, 0),
      turbineId: normalizedTurbineId,
      range,
      interval: config.intervalLabel,
      startsAt: new Date(startMs).toISOString(),
      endsAt: new Date(snapshotMs).toISOString(),
      snapshotAt: windFarm.lastUpdatedAt,
      deterministic: true as const,
    }),
  });
}
