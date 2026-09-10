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
    readonly range: ScadaHistoryRange | "CUSTOM";
    readonly interval: string;
    readonly startsAt: string;
    readonly endsAt: string;
    readonly snapshotAt: string;
    readonly deterministic: boolean;
  };
}

const hashText = (value: string): number => {
  let hash = 2_166_136_261;
  for (const character of value) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16_777_619);
  }
  return hash >>> 0;
};

const seededWave = (seed: number, index: number): number =>
  Math.sin((index + (seed % 37)) * 0.43) * 0.004 + Math.cos((index + (seed % 19)) * 0.17) * 0.002;

/**
 * Rewrite the complete fixture identity and signal semantics for a generic
 * asset. Generic turbines intentionally have no WT-023 anomaly or Agent event
 * provenance; values are deterministic healthy baselines derived per asset.
 */
function genericTurbineSeries(series: ScadaSeries, turbineId: string): ScadaSeries {
  const seed = hashText(`${turbineId}:${series.metric}`);
  const center = (series.normalRange[0] + series.normalRange[1]) / 2;
  const baseFactor = 0.91 + (seed % 120) / 1_000;
  const healthyCenter = series.metric === "anomaly-score" ? 0.18 + (seed % 8) / 100 : center;
  const points = series.points.map((point, index) => {
    const sourceRatio = series.currentValue === 0 ? 1 : point.value / series.currentValue;
    const candidate =
      series.metric === "wind-direction"
        ? (point.value + (seed % 53) + 360) % 360
        : series.metric === "anomaly-score"
          ? healthyCenter + seededWave(seed, index) * 8
          : healthyCenter *
            baseFactor *
            (0.985 + (sourceRatio - 1) * 0.2 + seededWave(seed, index));
    const bounded = Math.min(series.normalRange[1], Math.max(series.normalRange[0], candidate));
    return {
      ...point,
      value: Number(bounded.toFixed(series.precision)),
      quality: "good" as const,
      isAnomaly: false,
      aiEvent: null,
    };
  });
  return {
    ...series,
    id: `SCADA-${turbineId}-${series.metric}`,
    turbineId,
    currentValue: points.at(-1)?.value ?? 0,
    thresholds: series.thresholds.map((threshold) => ({
      ...threshold,
      id: `${turbineId}-${series.metric}-${threshold.severity}`,
    })),
    points,
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
  const sourceSeries = turbine
    ? scadaSeries.map((series) =>
        normalizedTurbineId === "WT-023"
          ? series
          : genericTurbineSeries(series, normalizedTurbineId),
      )
    : [];

  const data = Object.freeze(
    sourceSeries.map((series) => {
      const points = Object.freeze(
        Array.from({ length: config.samples }, (_, index) => {
          const ratio = config.samples === 1 ? 1 : index / (config.samples - 1);
          const sourceIndex = Math.round(ratio * (series.points.length - 1));
          const source = series.points[sourceIndex];
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
