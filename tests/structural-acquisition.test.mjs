import assert from "node:assert/strict";
import test from "node:test";
import {
  acquisitionHeader,
  awareTimestamp,
  optionalNumber,
  trainingModalIds,
} from "../lib/structural-acquisition.ts";

function waveform(extra = {}) {
  return {
    schema_version: "openvigil.waveform.v1",
    turbine_id: "SYNTHETIC-ACQ",
    started_at: "2026-10-05T08:00:00.123456+08:00",
    sample_rate_hz: 100000,
    channels: ["synthetic-X", "synthetic-Y"].map((channel_id) => ({
      channel_id,
      unit: "m/s2",
      offset_seconds: 0,
      samples: Array.from({ length: 16 }, (_, i) => i / 100),
    })),
    ...extra,
  };
}

test("metadata preserves the exact microsecond acquisition instant and end-exclusive bound", () => {
  const original = waveform();
  const bytes = JSON.stringify(original);
  assert.deepEqual(acquisitionHeader(bytes, "SYNTHETIC-ACQ"), {
    kind: "waveform",
    channel_ids: ["synthetic-X", "synthetic-Y"],
    started_at: "2026-10-05T08:00:00.123456+08:00",
    ended_at: "2026-10-05T00:00:00.123616Z",
    sample_rate_hz: 100000,
    sample_count: 16,
  });
  assert.equal(JSON.stringify(original), bytes);
  const rollover = acquisitionHeader(
    JSON.stringify(waveform({ started_at: "2026-10-05T23:59:59.999999Z", sample_rate_hz: 16 })),
    "SYNTHETIC-ACQ",
  );
  assert.equal(rollover.ended_at, "2026-10-06T00:00:00.999999Z");
});

test("missing samples, unequal channel lengths and synchronization offsets remain worker quality inputs", () => {
  const original = waveform();
  original.channels[0].samples[3] = null;
  original.channels[1].samples.push(0.1);
  original.channels[1].offset_seconds = 0.2;
  const text = JSON.stringify(original);
  const header = acquisitionHeader(text, "SYNTHETIC-ACQ");
  assert.equal(header.sample_count, 16);
  assert.equal(JSON.parse(text).channels[0].samples[3], null);
  assert.equal(JSON.parse(text).channels[1].samples.length, 17);
  assert.equal(JSON.parse(text).channels[1].offset_seconds, 0.2);
});

test("metadata rejects cross-asset, duplicate, malformed and unbounded signals", () => {
  for (const [input, message] of [
    [waveform({ turbine_id: "FOREIGN-ASSET" }), /机组不一致/],
    [waveform({ sample_rate_hz: 0 }), /采样率/],
    [waveform({ started_at: "2026-10-05T08:00:00" }), /时区/],
    [waveform({ channels: [waveform().channels[0], waveform().channels[0]] }), /不能重复/],
    [waveform({ channels: [{ ...waveform().channels[0], samples: [0] }] }), /原始采样点/],
    [
      waveform({ channels: [{ ...waveform().channels[0], samples: Array(16).fill("invalid") }] }),
      /采样点必须/,
    ],
    [waveform({ schema_version: "unversioned" }), /仅支持/],
  ])
    assert.throws(() => acquisitionHeader(JSON.stringify(input), "SYNTHETIC-ACQ"), message);
});

test("direct-force metadata retains instrument units and calibration without estimating force", () => {
  const header = acquisitionHeader(
    JSON.stringify({
      schema_version: "openvigil.direct-force.v1",
      tendon_id: "synthetic-tendon",
      sensor_id: "synthetic-force",
      observed_at: "2026-10-05T08:00:00.123456+08:00",
      value: 125000,
      unit: "N",
      calibration_version: "synthetic-cal1",
      uncertainty_kn: null,
    }),
    "SYNTHETIC-ACQ",
  );
  assert.deepEqual(header, {
    kind: "prestress",
    tendon_id: "synthetic-tendon",
    sensor_id: "synthetic-force",
    observed_at: "2026-10-05T08:00:00.123456+08:00",
    value: 125000,
    unit: "N",
    calibration_version: "synthetic-cal1",
  });
});

test("environment absence stays absent, measured zero stays zero and timestamps retain precision", () => {
  assert.equal(optionalNumber("", "temperature"), undefined);
  assert.equal(optionalNumber("  ", "temperature"), undefined);
  assert.equal(optionalNumber("0", "rotor"), 0);
  assert.equal(optionalNumber("-2.4", "temperature"), -2.4);
  assert.throws(() => optionalNumber("Infinity", "temperature"), /有限/);
  assert.equal(
    awareTimestamp("2026-10-05T08:00:00.123456+08:00"),
    "2026-10-05T08:00:00.123456+08:00",
  );
  assert.throws(() => awareTimestamp("2026-10-05T08:00:00"), /时区/);
});

test("baseline selection requires 30 real distinct references and never pads or silently deduplicates", () => {
  const ids = Array.from({ length: 30 }, (_, i) => `synthetic-mode-${i}`);
  assert.deepEqual(trainingModalIds(ids.join("\n")), ids);
  assert.throws(() => trainingModalIds(ids.slice(1).join("\n")), /30–256/);
  assert.throws(() => trainingModalIds(Array(30).fill(ids[0]).join("\n")), /不能重复/);
});
