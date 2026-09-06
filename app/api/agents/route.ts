import { agents, windFarm } from "@/lib";

import { collectionResponse } from "../_shared";

export function GET(): Response {
  return collectionResponse(agents, {
    snapshotAt: windFarm.lastUpdatedAt,
  });
}
