import { windFarm, workOrders } from "@/lib";

import { collectionResponse } from "../_shared";

export function GET(): Response {
  return collectionResponse(workOrders, {
    snapshotAt: windFarm.lastUpdatedAt,
  });
}
