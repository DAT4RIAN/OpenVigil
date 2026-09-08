import assert from "node:assert/strict";
import test from "node:test";

const workerUrl = new URL("../dist/server/index.js", import.meta.url);
workerUrl.searchParams.set("scada-history-test", `${process.pid}-${Date.now()}`);
const { default: worker } = await import(workerUrl.href);

const environment = {
  ASSETS: {
    fetch: async () => new Response("Not found", { status: 404 }),
  },
};

const context = {
  waitUntil() {},
  passThroughOnException() {},
};

async function fetchJson(path, expectedStatus = 200) {
  const response = await worker.fetch(
    new Request(new URL(path, "http://localhost"), {
      headers: { accept: "application/json" },
    }),
    environment,
    context,
  );

  assert.equal(response.status, expectedStatus, `${path} returned ${response.status}`);
  assert.match(response.headers.get("content-type") ?? "", /^application\/json\b/i);
  return response.json();
}

test("SCADA history ranges are distinct, deterministic, and preserve the WT-023 latest values", async () => {
  const samplesByRange = new Map([
    ["LIVE", 12],
    ["1H", 13],
    ["6H", 25],
    ["24H", 97],
    ["7D", 169],
    ["30D", 181],
  ]);

  for (const [range, samples] of samplesByRange) {
    const path = `/api/scada-history?turbineId=wt-023&range=${range}`;
    const [snapshot, repeated] = await Promise.all([fetchJson(path), fetchJson(path)]);

    assert.deepEqual(repeated, snapshot);
    assert.equal(snapshot.meta.range, range);
    assert.equal(snapshot.meta.turbineId, "WT-023");
    assert.equal(snapshot.meta.count, 17);
    assert.equal(snapshot.meta.pointCount, 17 * samples);
    assert.equal(snapshot.meta.deterministic, true);
    assert.ok(snapshot.data.every((series) => series.points.length === samples));
    assert.ok(Date.parse(snapshot.meta.startsAt) < Date.parse(snapshot.meta.endsAt));

    const vibration = snapshot.data.find(
      (series) => series.metric === "main-bearing-vibration-rms",
    );
    const temperature = snapshot.data.find(
      (series) => series.metric === "main-bearing-temperature",
    );
    assert.equal(vibration.currentValue, 4.81);
    assert.equal(temperature.currentValue, 76.4);
    assert.equal(vibration.points.at(-1).value, vibration.currentValue);
    assert.equal(temperature.points.at(-1).value, temperature.currentValue);
  }

  const invalid = await fetchJson("/api/scada-history?range=90D", 400);
  assert.equal(invalid.error.code, "INVALID_RANGE");

  const otherTurbine = await fetchJson("/api/scada-history?turbineId=WT-041&range=6H");
  assert.equal(otherTurbine.meta.turbineId, "WT-041");
  assert.equal(otherTurbine.meta.count, 17);
  assert.equal(otherTurbine.meta.pointCount, 17 * 25);
  assert.ok(otherTurbine.data.every((series) => series.turbineId === "WT-041"));
  assert.notEqual(
    otherTurbine.data.find((series) => series.metric === "main-bearing-vibration-rms").currentValue,
    4.81,
  );

  const missing = await fetchJson("/api/scada-history?turbineId=WT-999", 404);
  assert.equal(missing.error.code, "TURBINE_SCADA_NOT_FOUND");
});
