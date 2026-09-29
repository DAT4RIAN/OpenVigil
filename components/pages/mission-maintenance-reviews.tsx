import { StatusBadge, type StatusTone } from "@/components/data-display/status-badge";
import { Card, CardHeader, KeyValue } from "@/components/ui/primitives";
import { readMaintenanceReviews } from "@/lib/maintenance-review";

const labels: Readonly<Record<string, string>> = {
  engineering: "工程",
  safety: "安全",
  economic: "经济",
  resource: "资源",
  compliance: "合规",
};
const outcomes: Readonly<Record<string, { label: string; tone: StatusTone }>> = {
  pass: { label: "通过", tone: "success" },
  conditional_pass: { label: "有条件通过", tone: "warning" },
  fail: { label: "未通过", tone: "critical" },
};

export function MissionMaintenanceReviews({
  state,
  alternatives,
  recommendedId,
}: {
  readonly state: Readonly<Record<string, unknown>>;
  readonly alternatives: readonly {
    readonly alternative_id: string;
    readonly title?: string;
    readonly execution_plan_id?: string | null;
  }[];
  readonly recommendedId?: string;
}) {
  const { target, reviews, incomplete } = readMaintenanceReviews(state);
  const reviewed = alternatives.find((item) => item.alternative_id === target?.alternative_id);
  const recommended = alternatives.find((item) => item.alternative_id === recommendedId);
  const mismatch =
    target !== null &&
    (target.alternative_id !== recommendedId ||
      target.execution_plan_id !== recommended?.execution_plan_id);
  return (
    <Card>
      <div role="region" aria-label="维护方案审查">
        <CardHeader
          eyebrow={`${reviews.length} 项审查记录`}
          title="维护方案审查"
          description="核对维护方案的作业前提及机组运行限制，执行仍需人工批准。"
        />
        {target ? (
          <>
            <KeyValue label="审查对象" value={reviewed?.title ?? target.alternative_id} />
            <KeyValue label="审查范围" value="维护方案执行" />
            <details>
              <summary>作业计划追溯</summary>
              <code className="maintenance-review-target-id">
                {target.execution_plan_id ?? "尚未绑定作业计划"}
              </code>
            </details>
          </>
        ) : reviews.length > 0 ? (
          <p className="maintenance-review-warning">此审查未注明对象，请结合原始记录复核。</p>
        ) : null}
        {mismatch ? (
          <p className="maintenance-review-warning" role="alert">
            审查对象与当前推荐方案或作业计划不一致，请重新核对。
          </p>
        ) : null}
        {incomplete ? (
          <p className="maintenance-review-warning" role="alert">
            部分审查记录格式不完整，请刷新或检查原始记录。
          </p>
        ) : null}
        {reviews.some((review) => review.outcome === "fail") ? (
          <p className="maintenance-review-warning" role="alert">
            存在未通过的审查，请核对原因及作业条件。
          </p>
        ) : null}
        <div className="maintenance-review-list">
          {reviews.map((review, index) => {
            const outcome = Object.hasOwn(outcomes, review.outcome)
              ? outcomes[review.outcome]
              : { label: "未知结论", tone: "warning" as const };
            return (
              <article key={`${review.kind}-${index}`}>
                <div className="maintenance-review-heading">
                  <h3>
                    {Object.hasOwn(labels, review.kind) ? labels[review.kind] : review.kind}审查
                  </h3>
                  <StatusBadge
                    value={review.outcome}
                    label={outcome.label}
                    tone={outcome.tone}
                    compact
                  />
                </div>
                <small>{review.reviewer}</small>
                <p>{review.summary}</p>
                {review.conditions.length ? (
                  <>
                    <h4>作业前提</h4>
                    <ul>
                      {review.conditions.map((item, i) => (
                        <li key={i}>{item}</li>
                      ))}
                    </ul>
                  </>
                ) : null}
                {review.operatingConstraints.length ? (
                  <>
                    <h4>运行限制</h4>
                    <ul>
                      {review.operatingConstraints.map((item, i) => (
                        <li key={i}>{item}</li>
                      ))}
                    </ul>
                  </>
                ) : null}
              </article>
            );
          })}
          {!reviews.length ? <p>尚无审查记录。</p> : null}
        </div>
      </div>
    </Card>
  );
}
