import { failureCases, windFarm } from "@/lib";

import { collectionResponse } from "../_shared";

export function GET(): Response {
  return collectionResponse(failureCases, {
    scope: "archive",
    snapshotAt: windFarm.lastUpdatedAt,
  });
}
