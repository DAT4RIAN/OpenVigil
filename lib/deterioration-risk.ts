/** Unknown evidence must never be presented as a measured zero probability. */
export function deteriorationRiskPercent(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100
    ? value
    : null;
}

export function deteriorationRiskLabel(value: unknown): string {
  const percent = deteriorationRiskPercent(value);
  return percent === null ? "未评估" : `${percent}%`;
}
