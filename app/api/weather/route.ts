import { errorResponse } from "@/app/api/_shared";
import { CurrentWeatherError, readCurrentWeather } from "@/lib/current-weather";

export async function GET(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const unknownParameter = [...url.searchParams.keys()][0];
  if (unknownParameter) {
    return errorResponse(
      "INVALID_QUERY_PARAMETER",
      `Current weather accepts no parameters: ${unknownParameter}`,
    );
  }

  try {
    const result = await readCurrentWeather();
    return Response.json(
      {
        data: result.data,
        meta: {
          provider: "qweather",
          cacheStatus: result.cacheStatus,
          refreshSeconds: result.refreshSeconds,
        },
      },
      {
        headers: {
          "cache-control": `public, max-age=60, s-maxage=${result.refreshSeconds}, stale-while-revalidate=900`,
          "content-type": "application/json; charset=utf-8",
        },
      },
    );
  } catch (error) {
    if (error instanceof CurrentWeatherError) {
      return errorResponse(error.code, error.message, error.status);
    }
    return errorResponse(
      "CURRENT_WEATHER_UNAVAILABLE",
      "Current weather is currently unavailable.",
      503,
    );
  }
}
