import { alarms, windFarm } from "@/lib";

import { collectionResponse } from "../_shared";

export function GET(): Response {
  return collectionResponse(alarms, {
    snapshotAt: windFarm.lastUpdatedAt,
  });
}
