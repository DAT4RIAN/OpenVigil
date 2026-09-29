export function percentile(values, fraction) {
  if (!values.length || !Number.isFinite(fraction) || fraction <= 0 || fraction > 1) {
    throw new Error("A nonempty sample and a percentile in (0, 1] are required");
  }
  if (values.some((value) => !Number.isFinite(value) || value < 0)) {
    throw new Error("Measurements must be finite nonnegative numbers");
  }
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.ceil(sorted.length * fraction) - 1];
}

export function summarizeSamples(samples, metric, budgetMs, expectedCount) {
  if (
    !Number.isInteger(expectedCount) ||
    expectedCount < 1 ||
    !Number.isFinite(budgetMs) ||
    budgetMs < 0
  ) {
    throw new Error("A positive sample count and finite budget are required");
  }
  const measured = samples.filter(
    (sample) => Number.isFinite(sample[metric]) && sample[metric] >= 0,
  );
  const values = measured.map((sample) => sample[metric]);
  const failures = samples.filter((sample) => sample.error != null).length;
  const p95 = values.length ? percentile(values, 0.95) : null;
  return {
    expectedCount,
    sampleCount: samples.length,
    measuredCount: measured.length,
    failures,
    p50Ms: values.length ? percentile(values, 0.5) : null,
    p95Ms: p95,
    maximumMs: values.length ? Math.max(...values) : null,
    budgetMs,
    passed:
      samples.length === expectedCount &&
      measured.length === expectedCount &&
      failures === 0 &&
      p95 <= budgetMs,
  };
}

export function dataCounts(payload, collectionKeys) {
  if (collectionKeys) {
    if (!payload || payload.error || collectionKeys.some((key) => !Array.isArray(payload[key]))) {
      throw new Error("Invalid API collections");
    }
    return Object.fromEntries(collectionKeys.map((key) => [key, payload[key].length]));
  }
  if (!payload || payload.error || payload.data == null) throw new Error("Invalid API envelope");
  if (Array.isArray(payload.data)) return { rows: payload.data.length };
  if (typeof payload.data !== "object") throw new Error("Invalid API data");
  return Object.fromEntries(
    Object.entries(payload.data)
      .filter(([, value]) => Array.isArray(value))
      .map(([key, value]) => [key, value.length]),
  );
}
