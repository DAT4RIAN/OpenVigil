import { fleetSummary, windFarm } from "@/lib";

import { collectionResponse } from "../_shared";

export function GET(): Response {
  return collectionResponse([windFarm], {
    fleet: fleetSummary,
    snapshotAt: windFarm.lastUpdatedAt,
  });
}
