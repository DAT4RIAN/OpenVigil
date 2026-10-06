/** Missing measurements and planning estimates must not become zero-valued facts. */
export function decisionMoney(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value)
    ? `¥${(value / 10000).toFixed(1)} 万`
    : "未评估";
}

export function decisionQuantity(value: number | null | undefined, unit: string): string {
  return typeof value === "number" && Number.isFinite(value) ? `${value} ${unit}` : "未评估";
}

export function decisionConfidence(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? `${value}%` : "未量化";
}
