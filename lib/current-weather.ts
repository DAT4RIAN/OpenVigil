import { getWorkerEnv } from "./worker-env.ts";

const DEFAULT_REFRESH_SECONDS = 600;
const DEFAULT_STALE_SECONDS = 1_800;
const DEFAULT_TIMEOUT_MS = 5_000;

type WeatherEnvironmentName =
  | "WINDOPS_QWEATHER_API_HOST"
  | "WINDOPS_QWEATHER_API_KEY"
  | "WINDOPS_QWEATHER_DEVELOPER_ID"
  | "WINDOPS_QWEATHER_CREDENTIAL_ID"
  | "WINDOPS_WEATHER_LOCATION_NAME"
  | "WINDOPS_WEATHER_LATITUDE"
  | "WINDOPS_WEATHER_LONGITUDE"
  | "WINDOPS_WEATHER_REFRESH_SECONDS"
  | "WINDOPS_WEATHER_STALE_SECONDS"
  | "WINDOPS_WEATHER_TIMEOUT_MS";

export type CurrentWeatherCondition =
  "clear" | "partly-cloudy" | "cloudy" | "overcast" | "rain" | "snow" | "storm" | "fog" | "unknown";

export interface CurrentWeather {
  readonly locationName: string;
  readonly condition: CurrentWeatherCondition;
  readonly conditionCode: string;
  readonly conditionText: string;
  readonly temperatureC: number;
  readonly feelsLikeC: number;
  readonly windSpeedMps: number;
  readonly windDirection: string;
  readonly windDirectionDegrees: number;
  readonly windScale: number;
  readonly humidityPercent: number;
  readonly fetchedAt: string;
  readonly source: "qweather";
  readonly attributionUrls: readonly string[];
  readonly stale: boolean;
}

export interface CurrentWeatherResult {
  readonly data: CurrentWeather;
  readonly cacheStatus: "hit" | "miss" | "stale";
  readonly refreshSeconds: number;
}

interface CurrentWeatherConfig {
  readonly apiHost: string;
  readonly apiKey: string;
  readonly developerId: string | null;
  readonly credentialId: string | null;
  readonly locationName: string;
  readonly latitude: number;
  readonly longitude: number;
  readonly refreshSeconds: number;
  readonly staleSeconds: number;
  readonly timeoutMs: number;
}

interface CachedWeather {
  readonly key: string;
  readonly data: CurrentWeather;
  readonly freshUntil: number;
  readonly staleUntil: number;
}

type FetchWeather = (input: string | URL | Request, init?: RequestInit) => Promise<Response>;

export class CurrentWeatherError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status = 503) {
    super(message);
    this.name = "CurrentWeatherError";
    this.code = code;
    this.status = status;
  }
}

let cachedWeather: CachedWeather | null = null;
let pendingWeather: { readonly key: string; readonly request: Promise<CurrentWeather> } | null =
  null;

function configuredValue(name: WeatherEnvironmentName): string | undefined {
  const workerValue = getWorkerEnv()[name];
  if (typeof workerValue === "string") return workerValue;
  if (typeof process === "undefined") return undefined;
  return process.env[name];
}

function requiredValue(name: WeatherEnvironmentName, code: string): string {
  const value = configuredValue(name)?.trim();
  if (!value) {
    throw new CurrentWeatherError(code, `${name} is required for current weather.`);
  }
  return value;
}

function boundedNumber(name: WeatherEnvironmentName, minimum: number, maximum: number): number {
  const raw = requiredValue(name, "INVALID_WEATHER_LOCATION");
  const value = Number(raw);
  if (!Number.isFinite(value) || value < minimum || value > maximum) {
    throw new CurrentWeatherError(
      "INVALID_WEATHER_LOCATION",
      `${name} must be a number between ${minimum} and ${maximum}.`,
    );
  }
  return value;
}

function boundedInteger(
  name: WeatherEnvironmentName,
  fallback: number,
  minimum: number,
  maximum: number,
): number {
  const raw = configuredValue(name)?.trim();
  if (!raw) return fallback;
  if (!/^\d+$/.test(raw)) {
    throw new CurrentWeatherError(
      "INVALID_WEATHER_CONFIGURATION",
      `${name} must be an integer between ${minimum} and ${maximum}.`,
    );
  }
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    throw new CurrentWeatherError(
      "INVALID_WEATHER_CONFIGURATION",
      `${name} must be an integer between ${minimum} and ${maximum}.`,
    );
  }
  return value;
}

function normalizedApiHost(value: string): string {
  const candidate = value.includes("://") ? value : `https://${value}`;
  let url: URL;
  try {
    url = new URL(candidate);
  } catch {
    throw new CurrentWeatherError(
      "INVALID_QWEATHER_API_HOST",
      "WINDOPS_QWEATHER_API_HOST must be a valid QWeather API host.",
    );
  }
  const host = url.hostname.toLowerCase();
  if (
    url.protocol !== "https:" ||
    Boolean(url.username || url.password || url.search || url.hash) ||
    (url.pathname !== "/" && url.pathname !== "") ||
    (host !== "qweatherapi.com" && !host.endsWith(".qweatherapi.com"))
  ) {
    throw new CurrentWeatherError(
      "INVALID_QWEATHER_API_HOST",
      "WINDOPS_QWEATHER_API_HOST must be an HTTPS host under qweatherapi.com.",
    );
  }
  return url.origin;
}

function currentWeatherConfig(): CurrentWeatherConfig {
  const apiHost = normalizedApiHost(
    requiredValue("WINDOPS_QWEATHER_API_HOST", "QWEATHER_API_HOST_MISSING"),
  );
  const apiKey = requiredValue("WINDOPS_QWEATHER_API_KEY", "QWEATHER_API_KEY_MISSING");
  if (apiKey.length < 16 || apiKey.length > 256 || /\s/.test(apiKey)) {
    throw new CurrentWeatherError(
      "INVALID_QWEATHER_API_KEY",
      "WINDOPS_QWEATHER_API_KEY has an invalid format.",
    );
  }
  const locationName = requiredValue(
    "WINDOPS_WEATHER_LOCATION_NAME",
    "WEATHER_LOCATION_NAME_MISSING",
  );
  if (locationName.length > 80) {
    throw new CurrentWeatherError(
      "INVALID_WEATHER_LOCATION",
      "WINDOPS_WEATHER_LOCATION_NAME must not exceed 80 characters.",
    );
  }
  const refreshSeconds = boundedInteger(
    "WINDOPS_WEATHER_REFRESH_SECONDS",
    DEFAULT_REFRESH_SECONDS,
    60,
    3_600,
  );
  const staleSeconds = boundedInteger(
    "WINDOPS_WEATHER_STALE_SECONDS",
    DEFAULT_STALE_SECONDS,
    refreshSeconds,
    86_400,
  );
  return {
    apiHost,
    apiKey,
    developerId: configuredValue("WINDOPS_QWEATHER_DEVELOPER_ID")?.trim() || null,
    credentialId: configuredValue("WINDOPS_QWEATHER_CREDENTIAL_ID")?.trim() || null,
    locationName,
    latitude: boundedNumber("WINDOPS_WEATHER_LATITUDE", -90, 90),
    longitude: boundedNumber("WINDOPS_WEATHER_LONGITUDE", -180, 180),
    refreshSeconds,
    staleSeconds,
    timeoutMs: boundedInteger("WINDOPS_WEATHER_TIMEOUT_MS", DEFAULT_TIMEOUT_MS, 1_000, 15_000),
  };
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function normalizedCondition(text: string): CurrentWeatherCondition {
  if (/雷/.test(text)) return "storm";
  if (/雨/.test(text)) return "rain";
  if (/雪/.test(text)) return "snow";
  if (/雾|霾|沙|尘/.test(text)) return "fog";
  if (/阴/.test(text)) return "overcast";
  if (/少云|晴间多云/.test(text)) return "partly-cloudy";
  if (/多云/.test(text)) return "cloudy";
  if (/晴/.test(text)) return "clear";
  return "unknown";
}

const compassLabels: Readonly<Record<string, string>> = {
  n: "北风",
  nne: "东北偏北风",
  ne: "东北风",
  ene: "东北偏东风",
  e: "东风",
  ese: "东南偏东风",
  se: "东南风",
  sse: "东南偏南风",
  s: "南风",
  ssw: "西南偏南风",
  sw: "西南风",
  wsw: "西南偏西风",
  w: "西风",
  wnw: "西北偏西风",
  nw: "西北风",
  nnw: "西北偏北风",
  none: "无持续风向",
  vrb: "风向不定",
};

function parsedWeather(
  payload: unknown,
  config: CurrentWeatherConfig,
  fetchedAt: string,
): CurrentWeather {
  const root = record(payload);
  const condition = record(root?.condition);
  const temperature = record(root?.temperature);
  const feelsLike = record(root?.feelsLike);
  const wind = record(root?.wind);
  const windDirection = record(wind?.direction);
  const windSpeed = record(wind?.speed);
  const metadata = record(root?.metadata);
  const conditionText = typeof condition?.text === "string" ? condition.text.trim() : "";
  const conditionCode = typeof condition?.code === "string" ? condition.code.trim() : "";
  const temperatureC = finiteNumber(temperature?.value);
  const feelsLikeC = finiteNumber(feelsLike?.value);
  const windSpeedMps = finiteNumber(windSpeed?.value);
  const windDirectionDegrees = finiteNumber(windDirection?.degree);
  const windScale = finiteNumber(wind?.scale);
  const humidity = finiteNumber(root?.humidity);
  const compass = typeof windDirection?.compass === "string" ? windDirection.compass : "";
  if (
    !conditionText ||
    !conditionCode ||
    temperatureC === null ||
    feelsLikeC === null ||
    windSpeedMps === null ||
    windDirectionDegrees === null ||
    windScale === null ||
    humidity === null ||
    temperature?.unit !== "°C" ||
    feelsLike?.unit !== "°C" ||
    windSpeed?.unit !== "m/s"
  ) {
    throw new CurrentWeatherError(
      "INVALID_QWEATHER_RESPONSE",
      "QWeather returned an incomplete or incompatible current-weather response.",
      502,
    );
  }
  const attributions = Array.isArray(metadata?.attributions)
    ? metadata.attributions.filter((value): value is string => typeof value === "string")
    : [];
  return {
    locationName: config.locationName,
    condition: normalizedCondition(conditionText),
    conditionCode,
    conditionText,
    temperatureC,
    feelsLikeC,
    windSpeedMps,
    windDirection: compassLabels[compass.toLowerCase()] ?? (compass.toUpperCase() || "风向未知"),
    windDirectionDegrees,
    windScale,
    humidityPercent: Math.round(humidity * 100),
    fetchedAt,
    source: "qweather",
    attributionUrls: attributions,
    stale: false,
  };
}

function cacheKey(config: CurrentWeatherConfig): string {
  return [
    config.apiHost,
    config.apiKey,
    config.developerId ?? "",
    config.credentialId ?? "",
    config.locationName,
    config.latitude,
    config.longitude,
  ].join("|");
}

async function requestCurrentWeather(
  config: CurrentWeatherConfig,
  fetcher: FetchWeather,
  now: () => number,
): Promise<CurrentWeather> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), config.timeoutMs);
  const url = new URL(
    `/weather/v1/current/${encodeURIComponent(String(config.latitude))}/${encodeURIComponent(
      String(config.longitude),
    )}`,
    config.apiHost,
  );
  url.searchParams.set("lang", "zh");
  url.searchParams.set("localTime", "true");
  try {
    const response = await fetcher(url, {
      headers: {
        accept: "application/json",
        "x-qw-api-key": config.apiKey,
      },
      redirect: "error",
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new CurrentWeatherError(
        "QWEATHER_UPSTREAM_ERROR",
        `QWeather returned HTTP ${response.status}.`,
        502,
      );
    }
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      throw new CurrentWeatherError(
        "INVALID_QWEATHER_RESPONSE",
        "QWeather returned a non-JSON response.",
        502,
      );
    }
    return parsedWeather(payload, config, new Date(now()).toISOString());
  } catch (error) {
    if (error instanceof CurrentWeatherError) throw error;
    const timedOut = error instanceof DOMException && error.name === "AbortError";
    throw new CurrentWeatherError(
      timedOut ? "QWEATHER_TIMEOUT" : "QWEATHER_UNAVAILABLE",
      timedOut
        ? "QWeather did not respond before the configured deadline."
        : "QWeather is currently unavailable.",
      503,
    );
  } finally {
    clearTimeout(timeout);
  }
}

export async function readCurrentWeather(options?: {
  readonly fetcher?: FetchWeather;
  readonly now?: () => number;
}): Promise<CurrentWeatherResult> {
  const config = currentWeatherConfig();
  const now = options?.now ?? Date.now;
  const nowMs = now();
  const key = cacheKey(config);
  if (cachedWeather?.key === key && cachedWeather.freshUntil > nowMs) {
    return {
      data: cachedWeather.data,
      cacheStatus: "hit",
      refreshSeconds: config.refreshSeconds,
    };
  }
  const previous = cachedWeather?.key === key ? cachedWeather : null;
  try {
    if (pendingWeather?.key !== key) {
      pendingWeather = {
        key,
        request: requestCurrentWeather(config, options?.fetcher ?? fetch, now),
      };
    }
    const activeRequest = pendingWeather;
    const data = await activeRequest.request;
    cachedWeather = {
      key,
      data,
      freshUntil: nowMs + config.refreshSeconds * 1_000,
      staleUntil: nowMs + config.staleSeconds * 1_000,
    };
    return { data, cacheStatus: "miss", refreshSeconds: config.refreshSeconds };
  } catch (error) {
    if (previous && previous.staleUntil > nowMs) {
      return {
        data: { ...previous.data, stale: true },
        cacheStatus: "stale",
        refreshSeconds: config.refreshSeconds,
      };
    }
    throw error;
  } finally {
    if (pendingWeather?.key === key) pendingWeather = null;
  }
}

export function resetCurrentWeatherCacheForTests(): void {
  cachedWeather = null;
  pendingWeather = null;
}
