import { getTurbine, windFarm } from "@/lib/farm-data";
import { scadaSeries } from "@/lib/telemetry-data";

import { collectionResponse, turbineNotFoundResponse } from "../../../_shared";

interface TurbineScadaRouteContext {
  readonly params: Promise<{ readonly id: string }>;
}

export async function GET(_request: Request, context: TurbineScadaRouteContext): Promise<Response> {
  const { id } = await context.params;
  const turbine = getTurbine(id);

  if (!turbine) return turbineNotFoundResponse(id);

  const series = scadaSeries.filter((item) => item.turbineId === turbine.id);

  return collectionResponse(series, {
    turbineId: turbine.id,
    snapshotAt: windFarm.lastUpdatedAt,
  });
}
