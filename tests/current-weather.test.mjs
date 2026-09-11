import assert from "node:assert/strict";
import test from "node:test";

import {
  CurrentWeatherError,
  readCurrentWeather,
  resetCurrentWeatherCacheForTests,
} from "../lib/current-weather.ts";
import { enforceProductionRequestBoundary } from "../lib/production-runtime.ts";
import { runWithWorkerEnv } from "../lib/worker-env.ts";

const weatherEnvironment = {
  WINDOPS_QWEATHER_API_HOST: "weather-test.re.qweatherapi.com",
  WINDOPS_QWEATHER_API_KEY: "test-api-key-without-real-credentials",
  WINDOPS_QWEATHER_DEVELOPER_ID: "QTEST00001",
  WINDOPS_QWEATHER_CREDENTIAL_ID: "TESTCRED01",
  WINDOPS_WEATHER_LOCATION_NAME: "南京",
  WINDOPS_WEATHER_LATITUDE: "32.06",
  WINDOPS_WEATHER_LONGITUDE: "118.80",
  WINDOPS_WEATHER_REFRESH_SECONDS: "60",
  WINDOPS_WEATHER_STALE_SECONDS: "300",
  WINDOPS_WEATHER_TIMEOUT_MS: "1000",
};

function qweatherPayload({ text = "多云", code = "101" } = {}) {
  return {
    metadata: {
      tag: "weather-response-tag",
      attributions: ["https://developer.qweather.com/attribution.html"],
    },
    condition: { text, code },
    temperature: { value: 24.38, unit: "°C" },
    feelsLike: { value: 25.1, unit: "°C" },
    humidity: 0.69,
    wind: {
      direction: { degree: 45, compass: "ne" },
      speed: { value: 2.77, unit: "m/s" },
      scale: 2,
    },
  };
}

test("QWeather v1 uses the configured Nanjing coordinates and keeps the API key in a header", async () => {
  resetCurrentWeatherCacheForTests();
  let requestedUrl = "";
  let requestedHeaders = new Headers();
  const result = await runWithWorkerEnv(weatherEnvironment, () =>
    readCurrentWeather({
      now: () => Date.parse("2026-09-11T06:30:00Z"),
      fetcher: async (input, init) => {
        requestedUrl = String(input);
        requestedHeaders = new Headers(init?.headers);
        return Response.json(qweatherPayload());
      },
    }),
  );

  const url = new URL(requestedUrl);
  assert.equal(url.origin, "https://weather-test.re.qweatherapi.com");
  assert.equal(url.pathname, "/weather/v1/current/32.06/118.8");
  assert.equal(url.searchParams.get("lang"), "zh");
  assert.equal(url.searchParams.get("localTime"), "true");
  assert.equal(url.searchParams.has("key"), false);
  assert.equal(requestedHeaders.get("x-qw-api-key"), weatherEnvironment.WINDOPS_QWEATHER_API_KEY);
  assert.deepEqual(result, {
    data: {
      locationName: "南京",
      condition: "cloudy",
      conditionCode: "101",
      conditionText: "多云",
      temperatureC: 24.38,
      feelsLikeC: 25.1,
      windSpeedMps: 2.77,
      windDirection: "东北风",
      windDirectionDegrees: 45,
      windScale: 2,
      humidityPercent: 69,
      fetchedAt: "2026-09-11T06:30:00.000Z",
      source: "qweather",
      attributionUrls: ["https://developer.qweather.com/attribution.html"],
      stale: false,
    },
    cacheStatus: "miss",
    refreshSeconds: 60,
  });
});

test("weather cache returns fresh data without another provider request", async () => {
  resetCurrentWeatherCacheForTests();
  let calls = 0;
  let nowMs = Date.parse("2026-09-11T06:30:00Z");
  const fetcher = async () => {
    calls += 1;
    return Response.json(qweatherPayload({ text: "晴", code: "100" }));
  };

  const first = await runWithWorkerEnv(weatherEnvironment, () =>
    readCurrentWeather({ fetcher, now: () => nowMs }),
  );
  nowMs += 30_000;
  const second = await runWithWorkerEnv(weatherEnvironment, () =>
    readCurrentWeather({ fetcher, now: () => nowMs }),
  );

  assert.equal(first.cacheStatus, "miss");
  assert.equal(first.data.condition, "clear");
  assert.equal(second.cacheStatus, "hit");
  assert.equal(second.data.stale, false);
  assert.equal(calls, 1);
});

test("provider failure serves a marked stale value only inside the configured stale window", async () => {
  resetCurrentWeatherCacheForTests();
  let nowMs = Date.parse("2026-09-11T06:30:00Z");
  await runWithWorkerEnv(weatherEnvironment, () =>
    readCurrentWeather({
      now: () => nowMs,
      fetcher: async () => Response.json(qweatherPayload({ text: "阴", code: "104" })),
    }),
  );

  nowMs += 61_000;
  const stale = await runWithWorkerEnv(weatherEnvironment, () =>
    readCurrentWeather({
      now: () => nowMs,
      fetcher: async () => {
        throw new TypeError("simulated provider outage");
      },
    }),
  );
  assert.equal(stale.cacheStatus, "stale");
  assert.equal(stale.data.condition, "overcast");
  assert.equal(stale.data.stale, true);

  nowMs += 300_000;
  await assert.rejects(
    () =>
      runWithWorkerEnv(weatherEnvironment, () =>
        readCurrentWeather({
          now: () => nowMs,
          fetcher: async () => {
            throw new TypeError("simulated provider outage");
          },
        }),
      ),
    (error) =>
      error instanceof CurrentWeatherError &&
      error.code === "QWEATHER_UNAVAILABLE" &&
      !error.message.includes(weatherEnvironment.WINDOPS_QWEATHER_API_KEY),
  );
});

test("weather configuration rejects a missing or untrusted API host before calling fetch", async () => {
  resetCurrentWeatherCacheForTests();
  for (const apiHost of [undefined, "https://attacker.example/weather"]) {
    let called = false;
    await assert.rejects(
      () =>
        runWithWorkerEnv({ ...weatherEnvironment, WINDOPS_QWEATHER_API_HOST: apiHost }, () =>
          readCurrentWeather({
            fetcher: async () => {
              called = true;
              return Response.json(qweatherPayload());
            },
          }),
        ),
      (error) =>
        error instanceof CurrentWeatherError &&
        ["QWEATHER_API_HOST_MISSING", "INVALID_QWEATHER_API_HOST"].includes(error.code),
    );
    assert.equal(called, false);
  }
});

test("weather response validation rejects incompatible units instead of guessing", async () => {
  resetCurrentWeatherCacheForTests();
  const payload = qweatherPayload();
  payload.wind.speed.unit = "km/h";
  await assert.rejects(
    () =>
      runWithWorkerEnv(weatherEnvironment, () =>
        readCurrentWeather({ fetcher: async () => Response.json(payload) }),
      ),
    (error) => error instanceof CurrentWeatherError && error.code === "INVALID_QWEATHER_RESPONSE",
  );
});

test("the first-party weather route remains available behind the production boundary", () => {
  const productionEnvironment = {
    WINDOPS_RUNTIME_MODE: "production",
    WINDOPS_BACKEND_BASE_URL: "https://backend.example",
    WINDOPS_BACKEND_AUTH_MODE: "sites_delegation",
    WINDOPS_BACKEND_DELEGATION_SECRET:
      "weather-test-delegation-secret-with-at-least-forty-eight-characters",
    WINDOPS_BACKEND_EXPECTED_RELEASE_ID: "openvigil-weather-test",
    WINDOPS_BACKEND_EXPECTED_COMMIT_SHA: "a".repeat(40),
    WINDOPS_BACKEND_EXPECTED_IMAGE_DIGEST: `sha256:${"b".repeat(64)}`,
  };
  const response = runWithWorkerEnv(productionEnvironment, () =>
    enforceProductionRequestBoundary(new Request("https://openvigil.example/api/weather")),
  );
  assert.equal(response, null);
});
