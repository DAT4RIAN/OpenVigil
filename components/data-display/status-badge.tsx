import { cn } from "@/lib/utils";
import { localizedStatusLabel } from "@/lib/ui-localization";

export type StatusTone =
  "success" | "warning" | "critical" | "offline" | "info" | "maintenance" | "neutral";

const toneMap: Record<string, StatusTone> = {
  running: "success",
  normal: "success",
  healthy: "success",
  completed: "success",
  approved: "success",
  online: "success",
  working: "info",
  thinking: "info",
  investigating: "info",
  detected: "info",
  diagnosed: "info",
  executing: "info",
  "decision pending": "warning",
  "under review": "warning",
  reviewing: "warning",
  waiting: "warning",
  warning: "warning",
  watch: "warning",
  major: "warning",
  medium: "warning",
  degraded: "warning",
  critical: "critical",
  high: "critical",
  failed: "critical",
  offline: "offline",
  "communication lost": "offline",
  idle: "neutral",
  maintenance: "maintenance",
  low: "success",
  minor: "maintenance",
  info: "info",
};

export function StatusBadge({
  value,
  label,
  tone,
  pulse = false,
  compact = false,
}: {
  value: string;
  label?: string;
  tone?: StatusTone;
  pulse?: boolean;
  compact?: boolean;
}) {
  const resolved = tone ?? toneMap[value.toLowerCase()] ?? "neutral";
  return (
    <span
      className={cn(
        "status-badge",
        `status-badge--${resolved}`,
        compact && "status-badge--compact",
      )}
    >
      <span className={cn("status-dot", pulse && "status-dot--pulse")} aria-hidden="true" />
      {label ?? localizedStatusLabel(value)}
    </span>
  );
}

export function HealthBadge({ score }: { score: number }) {
  const tone: StatusTone = score >= 90 ? "success" : score >= 75 ? "warning" : "critical";
  return <StatusBadge value={String(score)} label={`${score} / 100`} tone={tone} compact />;
}
