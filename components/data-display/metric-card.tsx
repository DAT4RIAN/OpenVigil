import type { ReactNode } from "react";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { Card } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

export function MetricCard({
  label,
  value,
  unit,
  detail,
  change,
  changeLabel,
  icon,
  tone = "neutral",
}: {
  label: string;
  value: string;
  unit?: string;
  detail?: string;
  change?: number;
  changeLabel?: string;
  icon?: ReactNode;
  tone?: "neutral" | "success" | "warning" | "critical" | "info";
}) {
  const positive = typeof change === "number" && change >= 0;
  return (
    <Card className={cn("metric-card", `metric-card--${tone}`)}>
      <div className="metric-card__top">
        <span>{label}</span>
        {icon ? <span className="metric-card__icon">{icon}</span> : null}
      </div>
      <div className="metric-card__value">
        {value} {unit ? <small>{unit}</small> : null}
      </div>
      <div className="metric-card__footer">
        {typeof change === "number" ? (
          <span className={cn("metric-card__change", positive ? "positive" : "negative")}>
            {positive ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}
            {Math.abs(change)}%
          </span>
        ) : null}
        <span>{changeLabel ?? detail}</span>
      </div>
    </Card>
  );
}

