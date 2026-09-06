import type { TurbineStatus, WindFarm, WindTurbine } from "./types";

const FARM_ID = "WF-EAST-CHINA-01";
const TURBINE_COUNT = 64;
const RATED_POWER_MW = 6;
const SNAPSHOT_AT = "2026-08-13T10:30:00+08:00";

const round = (value: number, precision = 1): number => {
  const factor = 10 ** precision;
  return Math.round(value * factor) / factor;
};

const pad = (value: number, width = 3): string =>
  value.toString().padStart(width, "0");

const statusOverrides: Readonly<Partial<Record<number, TurbineStatus>>> = {
  7: "warning",
  18: "warning",
  23: "warning",
  41: "critical",
  52: "maintenance",
  64: "offline",
};

const healthOverrides: Readonly<Partial<Record<number, number>>> = {
  7: 82,
  12: 88,
  18: 85,
  23: 68,
  29: 89,
  33: 87,
  41: 56,
  52: 88,
  56: 86,
  64: 79,
};

const alarmCounts: Readonly<Partial<Record<number, number>>> = {
  3: 1,
  7: 1,
  12: 1,
  18: 2,
  23: 3,
  29: 1,
  33: 1,
  41: 4,
  45: 1,
  56: 1,
  60: 1,
};

const missionByTurbine: Readonly<Partial<Record<number, string>>> = {
  5: "MISSION-2026-0819",
  7: "MISSION-2026-0825",
  12: "MISSION-2026-0822",
  18: "MISSION-2026-0821",
  23: "MISSION-2026-0823",
  29: "MISSION-2026-0820",
  33: "MISSION-2026-0826",
  34: "MISSION-2026-0817",
  41: "MISSION-2026-0824",
  56: "MISSION-2026-0818",
};

const powerFor = (number: number, status: TurbineStatus): number => {
  if (status === "maintenance" || status === "offline") return 0;
  if (status === "communication-lost") return 0;
  if (number === 23) return 5.34;
  if (number === 7) return 4.86;
  if (number === 18) return 4.72;
  if (status === "critical") return 2.1;

  return round(
    Math.min(5.93, 5.33 + 0.42 * Math.sin(number * 0.73) + 0.16 * Math.cos(number * 0.31)),
    2,
  );
};

/**
 * A deterministic 8 x 8 offshore array. Operational values are generated from
 * each turbine number; special turbines are then overridden to tell the linked
 * demo stories used by alarms and missions.
 */
export const turbines: readonly WindTurbine[] = Array.from(
  { length: TURBINE_COUNT },
  (_, zeroBasedIndex): WindTurbine => {
    const number = zeroBasedIndex + 1;
    const status = statusOverrides[number] ?? "running";
    const row = Math.floor(zeroBasedIndex / 8) + 1;
    const column = (zeroBasedIndex % 8) + 1;
    const healthScore = healthOverrides[number] ?? 96 - ((number * 5) % 6);
    const windSpeedMps =
      number === 23
        ? 9.7
        : round(9.5 + 0.85 * Math.sin(number * 0.41) + 0.22 * Math.cos(number * 0.17), 1);
    const rotorSpeedRpm =
      number === 23
        ? 11.6
        : round(10.8 + (windSpeedMps - 8.8) * 0.72, 1);
    const lastMaintenanceDate = new Date(
      Date.UTC(2026, 5 + (number % 2), 2 + (number % 24), 1 + (number % 8)),
    ).toISOString();
    const nextInspectionDate = new Date(
      Date.UTC(2026, 8, 2 + (number % 25), 0, 0),
    ).toISOString();

    return {
      id: `WT-${pad(number)}`,
      farmId: FARM_ID,
      displayName: `WT-${pad(number)}`,
      model: "GW165-6.0MW",
      manufacturer: "Goldwind",
      serialNumber: `GW165-HDO-26-${pad(number, 4)}`,
      ratedPowerMW: RATED_POWER_MW,
      status,
      healthScore,
      powerMW: powerFor(number, status),
      windSpeedMps,
      rotorSpeedRpm,
      nacelleDirectionDeg: round(116 + ((number * 13) % 31) + 0.4 * Math.sin(number), 1),
      availabilityPercent:
        status === "offline"
          ? 0
          : status === "maintenance"
            ? 62.4
            : status === "critical"
              ? 78.2
              : round(96.8 + ((number * 11) % 25) / 10, 1),
      activeAlarmCount: alarmCounts[number] ?? 0,
      currentMissionId: missionByTurbine[number] ?? null,
      lastMaintenanceAt: lastMaintenanceDate,
      nextInspectionAt: nextInspectionDate,
      coordinates: {
        latitude: round(30.812 + (row - 1) * 0.014 + (column % 2) * 0.0018, 6),
        longitude: round(122.846 + (column - 1) * 0.018 + (row % 2) * 0.0021, 6),
      },
      gridPosition: {
        row,
        column,
        string: `${String.fromCharCode(64 + row)}${column}`,
      },
    };
  },
);

/** The cross-page focal asset for the main-bearing degradation demo. */
export const turbine023: WindTurbine = turbines[22];

const operatingStatuses: readonly TurbineStatus[] = [
  "running",
  "warning",
  "critical",
];

const currentPowerMW = round(
  turbines.reduce((total, turbine) => total + turbine.powerMW, 0),
  1,
);
const averageHealthScore = round(
  turbines.reduce((total, turbine) => total + turbine.healthScore, 0) /
    turbines.length,
  1,
);

export const windFarm: WindFarm = {
  id: FARM_ID,
  code: "ECOF-01",
  name: "华东海上风电场",
  nameEn: "East China Offshore Wind Farm",
  operator: "华东新能源运营中心",
  location: "东海近海示范区 · 离岸 38 km",
  timezone: "Asia/Shanghai",
  coordinates: { latitude: 30.862, longitude: 122.914 },
  commissionedAt: "2023-09-18T09:00:00+08:00",
  status: "operational",
  totalCapacityMW: TURBINE_COUNT * RATED_POWER_MW,
  turbineCount: turbines.length,
  turbineModel: "Goldwind GW165-6.0MW",
  operatingTurbines: turbines.filter((turbine) =>
    operatingStatuses.includes(turbine.status),
  ).length,
  maintenanceTurbines: turbines.filter(
    (turbine) => turbine.status === "maintenance",
  ).length,
  offlineTurbines: turbines.filter(
    (turbine) =>
      turbine.status === "offline" || turbine.status === "communication-lost",
  ).length,
  currentPowerMW,
  todayGenerationGWh: 3.81,
  averageHealthScore,
  activeAlarmCount: turbines.reduce(
    (total, turbine) => total + turbine.activeAlarmCount,
    0,
  ),
  activeMissionCount: 8,
  weatherSummary: "多云 · 东南风 9.7 m/s · 浪高 1.3 m",
  lastUpdatedAt: SNAPSHOT_AT,
};

export const fleetSummary = {
  total: turbines.length,
  operating: windFarm.operatingTurbines,
  warning: turbines.filter((turbine) => turbine.status === "warning").length,
  critical: turbines.filter((turbine) => turbine.status === "critical").length,
  maintenance: windFarm.maintenanceTurbines,
  offline: windFarm.offlineTurbines,
  ratedCapacityMW: windFarm.totalCapacityMW,
  currentPowerMW: windFarm.currentPowerMW,
  averageHealthScore: windFarm.averageHealthScore,
} as const;

