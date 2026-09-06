import { fleetSummary, turbines, windFarm } from "@/lib";

import { collectionResponse } from "../_shared";

export function GET(): Response {
  return collectionResponse(turbines, {
    farmId: windFarm.id,
    fleet: fleetSummary,
    snapshotAt: windFarm.lastUpdatedAt,
  });
}
