import { alarmArchive, alarms, windFarm } from "@/lib";

import { collectionResponse, errorResponse } from "../_shared";

export function GET(request: Request): Response {
  const requestedScope = new URL(request.url).searchParams.get("scope");

  if (requestedScope !== null && requestedScope !== "live" && requestedScope !== "archive") {
    return errorResponse(
      "INVALID_SCOPE",
      'The scope query parameter must be either "live" or "archive".',
    );
  }

  const scope = requestedScope ?? "live";
  const data = scope === "archive" ? alarmArchive : alarms;

  return collectionResponse(data, {
    scope,
    snapshotAt: windFarm.lastUpdatedAt,
  });
}
