import { SCADA_HISTORY_RANGES, getScadaHistory, type ScadaHistoryRange } from "@/lib/scada-history";
import { productionScadaHistoryResponse } from "@/lib/production-domain-adapter";
import { getProductionBackendConfig } from "@/lib/production-runtime";

import { jsonResponse } from "../_shared";

export function GET(request: Request): Response | Promise<Response> {
  if (getProductionBackendConfig().mode === "production") {
    return productionScadaHistoryResponse(request);
  }
  const url = new URL(request.url);
  const rawRange = (url.searchParams.get("range") ?? "24H").trim().toUpperCase();
  const turbineId = (url.searchParams.get("turbineId") ?? "WT-023").trim().toUpperCase();

  if (!SCADA_HISTORY_RANGES.includes(rawRange as ScadaHistoryRange)) {
    return jsonResponse(
      {
        error: {
          code: "INVALID_RANGE",
          message: `range must be one of ${SCADA_HISTORY_RANGES.join(", ")}`,
        },
      },
      400,
    );
  }

  const snapshot = getScadaHistory(rawRange as ScadaHistoryRange, turbineId);
  if (!snapshot.data.length) {
    return jsonResponse(
      { error: { code: "TURBINE_SCADA_NOT_FOUND", message: `No SCADA history for ${turbineId}` } },
      404,
    );
  }
  return jsonResponse(snapshot);
}
