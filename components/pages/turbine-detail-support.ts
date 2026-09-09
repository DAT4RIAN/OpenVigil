import type { SubsystemHealth } from "@/lib/types";

export const turbineDetailTabs = [
  "Overview",
  "SCADA",
  "Health",
  "Alarms",
  "Missions",
  "Maintenance",
  "Documents",
] as const;

export type TurbineDetailTab = (typeof turbineDetailTabs)[number];

export function subsystemStateLabel(state: SubsystemHealth["state"]): string {
  const labels: Record<SubsystemHealth["state"], string> = {
    healthy: "健康",
    watch: "关注",
    degraded: "退化",
    critical: "严重",
    maintenance: "维护",
    offline: "离线",
  };
  return labels[state];
}
