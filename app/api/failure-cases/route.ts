import { failureCases } from "@/lib/archive-data";
import { windFarm } from "@/lib/farm-data";

import { collectionResponse } from "../_shared";

export function GET(): Response {
  return collectionResponse(failureCases, {
    scope: "archive",
    snapshotAt: windFarm.lastUpdatedAt,
  });
}
