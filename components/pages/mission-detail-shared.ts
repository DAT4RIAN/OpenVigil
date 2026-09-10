export const missionProgressSteps = [
  "已发现",
  "调查中",
  "已诊断",
  "决策",
  "审核",
  "已批准",
  "执行中",
  "已完成",
];
export function formatMissionTime(timestamp: string) {
  return new Date(timestamp).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}
