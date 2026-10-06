import type { AgentToolArguments } from "./contracts";
import { resolveResourceScope } from "./helpers";
import { sparePartStatusValues, vesselTypeValues } from "./catalog";
import { maintenanceCrews, serviceVessels, spareParts } from "../resource-data";
import { windFarm } from "../farm-data";
import type { ResourceAvailability } from "../types";

export const querySpareParts = (args: AgentToolArguments): unknown => {
  const scope = resolveResourceScope(args);
  const hasScope = scope.turbineId !== null || scope.workOrderId !== null;
  const partNumber = (args.partNumber as string | undefined) ?? null;
  const status = (args.status as (typeof sparePartStatusValues)[number] | undefined) ?? null;
  const limit = args.limit as number;
  const matching = spareParts
    .filter(
      (part) =>
        (!hasScope ||
          part.reservedForWorkOrderIds.some((id) => scope.linkedWorkOrderIds.includes(id))) &&
        (!partNumber || part.partNumber.toUpperCase() === partNumber) &&
        (!status || part.status === status),
    )
    .sort(
      (left, right) =>
        left.available - right.available || left.partNumber.localeCompare(right.partNumber),
    );

  return {
    snapshotAt: windFarm.lastUpdatedAt,
    scope,
    filters: { partNumber, status },
    total: matching.length,
    returned: Math.min(limit, matching.length),
    totals: {
      onHand: matching.reduce((sum, part) => sum + part.onHand, 0),
      reserved: matching.reduce((sum, part) => sum + part.reserved, 0),
      available: matching.reduce((sum, part) => sum + part.available, 0),
    },
    spareParts: matching.slice(0, limit),
  };
};

export const queryCrew = (args: AgentToolArguments): unknown => {
  const scope = resolveResourceScope(args);
  const hasScope = scope.turbineId !== null || scope.workOrderId !== null;
  const availability = (args.availability as ResourceAvailability | undefined) ?? null;
  const specialty = (args.specialty as string | undefined) ?? null;
  const limit = args.limit as number;
  const matching = maintenanceCrews
    .filter(
      (crew) =>
        (!hasScope ||
          (crew.assignedWorkOrderId !== null &&
            scope.linkedWorkOrderIds.includes(crew.assignedWorkOrderId))) &&
        (!availability || crew.availability === availability) &&
        (!specialty || crew.specialties.some((item) => item.toLowerCase().includes(specialty))),
    )
    .sort((left, right) => left.id.localeCompare(right.id));

  return {
    snapshotAt: windFarm.lastUpdatedAt,
    scope,
    filters: { availability, specialty },
    total: matching.length,
    returned: Math.min(limit, matching.length),
    crews: matching.slice(0, limit),
  };
};

export const queryVessels = (args: AgentToolArguments): unknown => {
  const scope = resolveResourceScope(args);
  const hasScope = scope.turbineId !== null || scope.workOrderId !== null;
  const availability = (args.availability as ResourceAvailability | undefined) ?? null;
  const vesselType = (args.vesselType as (typeof vesselTypeValues)[number] | undefined) ?? null;
  const limit = args.limit as number;
  const matching = serviceVessels
    .filter(
      (vessel) =>
        (!hasScope ||
          (vessel.assignedWorkOrderId !== null &&
            scope.linkedWorkOrderIds.includes(vessel.assignedWorkOrderId))) &&
        (!availability || vessel.availability === availability) &&
        (!vesselType || vessel.vesselType.toLowerCase() === vesselType),
    )
    .sort((left, right) => left.id.localeCompare(right.id));

  return {
    snapshotAt: windFarm.lastUpdatedAt,
    scope,
    filters: { availability, vesselType },
    total: matching.length,
    returned: Math.min(limit, matching.length),
    vessels: matching.slice(0, limit),
  };
};
