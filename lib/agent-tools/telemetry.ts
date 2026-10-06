import type { AgentToolArguments } from "./contracts";
import { aggregateNumbers, requiredTurbine, round } from "./helpers";
import type {
  AlarmSeverity,
  AlarmStatus,
  ScadaMetric,
  SubsystemKey,
  WeatherSuitability,
} from "../types";
import { alarmArchive, queryScadaMeasurements } from "../archive-data";
import { windFarm } from "../farm-data";
import { scadaSeries, weatherWindows } from "../telemetry-data";
import { AgentToolRuntimeError } from "./contracts";

export const queryScada = (args: AgentToolArguments): unknown => {
  const turbineId = args.turbineId as string;
  requiredTurbine(turbineId);
  const metric = args.metric as ScadaMetric | undefined;
  const limit = args.limit as number;
  const summary = queryScadaMeasurements({ turbineId, metric, limit: 0 });
  const offset = (args.offset as number | undefined) ?? Math.max(0, summary.total - limit);
  const page = queryScadaMeasurements({ turbineId, metric, limit, offset });
  const values = page.items.map((item) => item.value);

  return {
    snapshotAt: page.snapshotAt,
    turbineId,
    metric: metric ?? null,
    page: { offset: page.offset, limit: page.limit, count: page.items.length, total: page.total },
    aggregate: {
      ...aggregateNumbers(values),
      anomalyCount: page.items.filter((item) => item.isAnomaly).length,
      badOrUncertainQualityCount: page.items.filter((item) => item.quality !== "good").length,
    },
    measurements: page.items,
  };
};

export const queryAlarmHistory = (args: AgentToolArguments): unknown => {
  const turbineId = args.turbineId as string;
  requiredTurbine(turbineId);
  const subsystem = args.subsystem as SubsystemKey | undefined;
  const severity = args.severity as AlarmSeverity | undefined;
  const status = args.status as AlarmStatus | undefined;
  const limit = args.limit as number;
  const filtered = alarmArchive
    .filter(
      (alarm) =>
        alarm.turbineId === turbineId &&
        (!subsystem || alarm.subsystem === subsystem) &&
        (!severity || alarm.severity === severity) &&
        (!status || alarm.status === status),
    )
    .sort(
      (left, right) =>
        Date.parse(right.triggeredAt) - Date.parse(left.triggeredAt) ||
        left.id.localeCompare(right.id),
    );
  const items = filtered.slice(0, limit);

  return {
    snapshotAt: windFarm.lastUpdatedAt,
    turbineId,
    filters: { subsystem: subsystem ?? null, severity: severity ?? null, status: status ?? null },
    total: filtered.length,
    returned: items.length,
    counts: {
      active: filtered.filter((alarm) => alarm.status === "active").length,
      acknowledged: filtered.filter((alarm) => alarm.status === "acknowledged").length,
      resolved: filtered.filter((alarm) => alarm.status === "resolved").length,
      criticalOrMajor: filtered.filter(
        (alarm) => alarm.severity === "critical" || alarm.severity === "major",
      ).length,
    },
    alarms: items,
  };
};

export const queryVibration = (args: AgentToolArguments): unknown => {
  const turbineId = args.turbineId as string;
  requiredTurbine(turbineId);
  const limit = args.limit as number;
  const metric: ScadaMetric = "main-bearing-vibration-rms";
  const summary = queryScadaMeasurements({ turbineId, metric, limit: 0 });
  const page = queryScadaMeasurements({
    turbineId,
    metric,
    limit,
    offset: Math.max(0, summary.total - limit),
  });
  const configuredSeries = scadaSeries.find(
    (series) => series.turbineId === turbineId && series.metric === metric,
  );
  const first = page.items[0]?.value ?? null;
  const latest = page.items.at(-1)?.value ?? null;

  return {
    snapshotAt: page.snapshotAt,
    turbineId,
    metric,
    measurementType: "RMS time-series archive",
    unit: page.items[0]?.unit ?? configuredSeries?.unit ?? "mm/s",
    currentRms: latest,
    changeFromWindowStartPercent:
      first === null || latest === null || first === 0
        ? null
        : round(((latest - first) / first) * 100, 1),
    normalRange: configuredSeries?.normalRange ?? null,
    thresholds: configuredSeries?.thresholds ?? [],
    anomalyCount: page.items.filter((item) => item.isAnomaly).length,
    measurements: page.items,
  };
};

export const queryWeather = (args: AgentToolArguments): unknown => {
  const farmId = args.farmId as string;
  if (farmId !== windFarm.id) {
    throw new AgentToolRuntimeError(
      "WIND_FARM_NOT_FOUND",
      `Wind farm ${farmId} was not found.`,
      404,
      {
        farmId,
      },
    );
  }
  const suitability = args.suitability as WeatherSuitability | undefined;
  const limit = args.limit as number;
  const matching = weatherWindows
    .filter(
      (window) => window.farmId === farmId && (!suitability || window.suitability === suitability),
    )
    .sort(
      (left, right) =>
        Date.parse(left.startsAt) - Date.parse(right.startsAt) || left.id.localeCompare(right.id),
    );

  return {
    snapshotAt: windFarm.lastUpdatedAt,
    farmId,
    suitability: suitability ?? null,
    total: matching.length,
    recommendedWindowId: matching.find((window) => window.suitability === "suitable")?.id ?? null,
    windows: matching.slice(0, limit),
  };
};
