import { missions, windFarm } from "@/lib";

import { collectionResponse } from "../_shared";

export function GET(): Response {
  return collectionResponse(missions, {
    snapshotAt: windFarm.lastUpdatedAt,
  });
}
