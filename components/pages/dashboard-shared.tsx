"use client";

import { ArrowRight, CheckCircle2 } from "lucide-react";

export function formatTime(timestamp: string) {
  return new Date(timestamp).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function formatDurationMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes} 分钟`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder ? `${hours} 小时 ${remainder} 分钟` : `${hours} 小时`;
}

type DashboardIncidentStripProps = {
  readonly stable: boolean;
  readonly priority: "P1" | "P2" | "稳定";
  readonly eyebrow: string;
  readonly title: string;
  readonly context: string;
  readonly aiStatus: string;
  readonly healthValue: string;
  readonly anomalyValue: string;
  readonly freshness: string;
  readonly actionHref: string;
  readonly actionLabel: string;
};

export function DashboardIncidentStrip({
  stable,
  priority,
  eyebrow,
  title,
  context,
  aiStatus,
  healthValue,
  anomalyValue,
  freshness,
  actionHref,
  actionLabel,
}: DashboardIncidentStripProps) {
  return (
    <section
      className={`command-strip${stable ? " command-strip--stable" : ""}`}
      aria-label={stable ? "当前稳定状态" : "当前最高优先级事件"}
      aria-live="polite"
    >
      <span className="incident-index" data-stable={stable || undefined}>
        {stable ? <CheckCircle2 size={18} aria-hidden="true" /> : priority}
      </span>
      <span className="incident-copy">
        <small>{eyebrow}</small>
        <a className="incident-title-link" href={actionHref}>
          {title}
        </a>
        <span>{context}</span>
      </span>
      <dl className="incident-signals">
        <div>
          <dt>公开 AI 状态</dt>
          <dd>{aiStatus}</dd>
        </div>
        <div>
          <dt>健康值</dt>
          <dd>{healthValue}</dd>
        </div>
        <div>
          <dt>异常强度</dt>
          <dd>{anomalyValue}</dd>
        </div>
        <div>
          <dt>数据时间</dt>
          <dd>{freshness}</dd>
        </div>
      </dl>
      <a className="incident-link" href={actionHref}>
        {actionLabel} <ArrowRight size={15} aria-hidden="true" />
      </a>
    </section>
  );
}
