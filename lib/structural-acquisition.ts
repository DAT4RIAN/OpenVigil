export const MAX_STRUCTURAL_BYTES = 32 * 1024 * 1024;

export function jsonObject(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("资料必须为 JSON 对象。");
  return value as Record<string, unknown>;
}

export function awareTimestamp(value: string): string {
  if (
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})$/i.test(value) ||
    !Number.isFinite(Date.parse(value))
  )
    throw new Error("时间必须包含 Z 或明确时区偏移，例如 +08:00。");
  // Native acquisition timestamps can have microseconds; Date would truncate
  // them and make the submitted header disagree with the immutable raw bytes.
  return value;
}

function endExclusive(start: string, samples: number, rate: number): string {
  const match = /^(.*?)(?:\.(\d{1,6}))?(Z|[+-]\d{2}:\d{2})$/i.exec(start);
  if (!match) throw new Error("采集时间格式无效。");
  const seconds = Date.parse(`${match[1]}${match[3]}`);
  const micros =
    BigInt(seconds) * BigInt(1000) +
    BigInt((match[2] ?? "").padEnd(6, "0")) +
    BigInt(Math.round((samples / rate) * 1000000));
  const wholeSeconds =
    micros >= BigInt(0) ? micros / BigInt(1000000) : (micros - BigInt(999999)) / BigInt(1000000);
  const fractional = micros - wholeSeconds * BigInt(1000000);
  return `${new Date(Number(wholeSeconds) * 1000).toISOString().slice(0, 19)}.${fractional.toString().padStart(6, "0")}Z`;
}

export function optionalNumber(value: string, name: string): number | undefined {
  if (!value.trim()) return undefined;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) throw new Error(`${name}必须为有限数值。`);
  return parsed;
}

function identity(value: unknown): string {
  if (typeof value !== "string" || !value || value.length > 36)
    throw new Error("资料中的对象 ID 不符合格式。");
  return value;
}

export interface WaveformHeader {
  readonly kind: "waveform";
  readonly channel_ids: readonly string[];
  readonly started_at: string;
  readonly ended_at: string;
  readonly sample_rate_hz: number;
  readonly sample_count: number;
}
export interface DirectForceHeader {
  readonly kind: "prestress";
  readonly tendon_id: string;
  readonly sensor_id: string;
  readonly observed_at: string;
  readonly value: number;
  readonly unit: "N" | "kN";
  readonly calibration_version: string;
}

/** Read acquisition metadata; quality failures remain for the actual worker. */
export function acquisitionHeader(
  text: string,
  turbineId: string,
): WaveformHeader | DirectForceHeader {
  const body = jsonObject(JSON.parse(text));
  if (body.schema_version === "openvigil.direct-force.v1") {
    if (
      typeof body.value !== "number" ||
      !Number.isFinite(body.value) ||
      body.value < 0 ||
      !["N", "kN"].includes(String(body.unit)) ||
      typeof body.calibration_version !== "string"
    )
      throw new Error("直接索力资料缺少有效的读数、单位或校准版本。");
    return {
      kind: "prestress",
      tendon_id: identity(body.tendon_id),
      sensor_id: identity(body.sensor_id),
      observed_at: awareTimestamp(String(body.observed_at)),
      value: body.value,
      unit: body.unit as "N" | "kN",
      calibration_version: body.calibration_version,
    };
  }
  if (body.schema_version !== "openvigil.waveform.v1")
    throw new Error("仅支持原始波形或直接索力的 OpenVigil JSON 格式。");
  if (body.turbine_id !== turbineId) throw new Error("波形所属机组与当前授权机组不一致。");
  if (
    typeof body.sample_rate_hz !== "number" ||
    !Number.isFinite(body.sample_rate_hz) ||
    body.sample_rate_hz <= 0 ||
    body.sample_rate_hz > 100000 ||
    !Array.isArray(body.channels) ||
    !body.channels.length ||
    body.channels.length > 16
  )
    throw new Error("波形采样率或通道数量不符合计算边界。");
  const channels = body.channels.map(jsonObject);
  const channelIds = channels.map((row) => identity(row.channel_id));
  if (new Set(channelIds).size !== channelIds.length) throw new Error("波形通道不能重复。");
  let total = 0;
  for (const row of channels) {
    if (!Array.isArray(row.samples) || row.samples.length < 16 || row.samples.length > 262144)
      throw new Error("每个通道必须包含 16–262144 个原始采样点。");
    total += row.samples.length;
    // Missing points and synchronization offsets are preserved, not repaired.
    if (
      row.samples.some(
        (sample) => sample !== null && (typeof sample !== "number" || !Number.isFinite(sample)),
      )
    )
      throw new Error("采样点必须是有限数值或明确缺失的 null。");
  }
  if (total > 1048576) throw new Error("波形超过一百万个采样点的计算边界。");
  const started = awareTimestamp(String(body.started_at));
  const sampleCount = (channels[0].samples as unknown[]).length;
  return {
    kind: "waveform",
    channel_ids: channelIds,
    started_at: started,
    ended_at: endExclusive(started, sampleCount, body.sample_rate_hz),
    sample_rate_hz: body.sample_rate_hz,
    sample_count: sampleCount,
  };
}

export function trainingModalIds(text: string): string[] {
  const ids = text
    .trim()
    .split(/[\s,]+/)
    .filter(Boolean);
  if (ids.length < 30 || ids.length > 256)
    throw new Error("基线需要 30–256 个健康窗口的模态观测 ID。");
  if (new Set(ids).size !== ids.length) throw new Error("训练观测 ID 不能重复。");
  return ids.map(identity);
}

export interface RegisteredStructuralObject {
  readonly id: string;
  readonly [key: string]: unknown;
}
export function isStructuralObject(value: unknown): value is RegisteredStructuralObject {
  return Boolean(
    value && typeof value === "object" && typeof (value as { id?: unknown }).id === "string",
  );
}
