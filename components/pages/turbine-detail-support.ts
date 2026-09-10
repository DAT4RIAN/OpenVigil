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

export const turbineDetailTabLabels: Record<TurbineDetailTab, string> = {
  Overview: "概览",
  SCADA: "SCADA",
  Health: "健康",
  Alarms: "告警",
  Missions: "Mission",
  Maintenance: "维护",
  Documents: "文档",
};

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
