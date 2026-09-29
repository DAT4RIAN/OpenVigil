export interface MaintenanceReviewTarget {
  readonly scope: "maintenance_execution";
  readonly alternative_id: string;
  readonly execution_plan_id: string | null;
}

export interface MaintenanceReview {
  readonly kind: string;
  readonly reviewer: string;
  readonly outcome: string;
  readonly summary: string;
  readonly conditions: readonly string[];
  readonly operatingConstraints: readonly string[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function strings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function malformedList(value: unknown): boolean {
  return (
    value !== undefined && (!Array.isArray(value) || value.some((item) => typeof item !== "string"))
  );
}

export function readMaintenanceReviews(state: Readonly<Record<string, unknown>>) {
  const rawTarget = state.review_target;
  const target: MaintenanceReviewTarget | null =
    isRecord(rawTarget) &&
    rawTarget.scope === "maintenance_execution" &&
    typeof rawTarget.alternative_id === "string" &&
    rawTarget.alternative_id.trim().length > 0 &&
    (rawTarget.execution_plan_id === null ||
      (typeof rawTarget.execution_plan_id === "string" &&
        rawTarget.execution_plan_id.trim().length > 0))
      ? {
          scope: "maintenance_execution",
          alternative_id: rawTarget.alternative_id,
          execution_plan_id: rawTarget.execution_plan_id,
        }
      : null;
  let incomplete =
    (rawTarget !== undefined && rawTarget !== null && target === null) ||
    (state.reviews !== undefined && !Array.isArray(state.reviews));
  const reviews: MaintenanceReview[] = [];
  for (const item of Array.isArray(state.reviews) ? state.reviews : []) {
    if (!isRecord(item)) {
      incomplete = true;
      continue;
    }
    if (
      typeof item.review_type !== "string" ||
      typeof item.public_summary !== "string" ||
      !["pass", "conditional_pass", "fail"].includes(String(item.outcome)) ||
      malformedList(item.conditions) ||
      malformedList(item.operating_constraints)
    )
      incomplete = true;
    reviews.push({
      kind: typeof item.review_type === "string" ? item.review_type : "unknown",
      reviewer: typeof item.reviewer_agent === "string" ? item.reviewer_agent : "未注明审查人",
      outcome: typeof item.outcome === "string" ? item.outcome : "unknown",
      summary: typeof item.public_summary === "string" ? item.public_summary : "未提供审查摘要。",
      conditions: strings(item.conditions),
      operatingConstraints: strings(item.operating_constraints),
    });
  }
  return { target, reviews, incomplete };
}
