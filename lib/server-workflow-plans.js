export const SERVER_WORKFLOW_ALTERNATIVE_IDS = ["ALT-0823-A", "ALT-0823-B", "ALT-0823-C"];

/** Runtime-safe plan catalog shared by the browser bundle and Node strip-types tests. */
export const serverWorkflowAlternativePlans = {
  "ALT-0823-A": {
    id: "ALT-0823-A",
    label: "方案 A",
    title: "立即停机检查",
    description: "立即停机并等待首个可用海况窗口，对主轴承实施完整检查。",
    workOrderIssue: "方案 A · WT-023 主轴承立即停机检查",
    workOrderDescription: "立即停机、执行 LOTO，并对主轴承润滑、振动、温度和滚道实施完整检查。",
    assignedTeam: "海维二组 · 4 人",
    estimatedDurationHours: 8,
    taskTitles: [
      "完成立即停机与 LOTO，并检查润滑状态、采集润滑脂样本",
      "使用便携式分析仪采集停机前三向振动数据",
      "复核驱动端与非驱动端轴承温度",
      "执行滚道与滚子内窥镜检查",
      "上传停机、现场照片、频谱和检查结论",
    ],
    requiredTools: ["便携式振动分析仪", "工业内窥镜", "红外测温仪", "润滑脂取样套件"],
    ppeRequirements: ["全身式安全带", "海上救生衣", "防滑安全鞋", "护目镜", "耐油手套"],
    safetyProcedures: [
      "立即停止 WT-023 并执行机械锁定与电气 LOTO",
      "确认轮毂锁定销完全就位后方可进入机舱",
      "CTV 靠泊浪高不得超过 1.8 m",
    ],
  },
  "ALT-0823-B": {
    id: "ALT-0823-B",
    label: "方案 B",
    title: "降载运行并在 72 小时内检查",
    description: "将机组限制至额定功率 70%，提高采样频率，并在 8 月 14 日窗口现场检查。",
    workOrderIssue: "方案 B · WT-023 主轴承降载后检查",
    workOrderDescription: "执行降载后的主轴承润滑、振动、温度与内窥镜联合检查。",
    assignedTeam: "海维二组 · 4 人",
    estimatedDurationHours: 6.5,
    taskTitles: [
      "检查主轴承润滑状态并采集润滑脂样本",
      "使用便携式分析仪采集三向振动数据",
      "复核驱动端与非驱动端轴承温度",
      "执行滚道与滚子内窥镜检查",
      "上传现场照片、频谱和检查结论",
    ],
    requiredTools: ["便携式振动分析仪", "工业内窥镜", "红外测温仪", "润滑脂取样套件"],
    ppeRequirements: ["全身式安全带", "海上救生衣", "防滑安全鞋", "护目镜", "耐油手套"],
    safetyProcedures: [
      "现场检查前执行停机、机械锁定与电气 LOTO",
      "确认轮毂锁定销完全就位",
      "CTV 靠泊浪高不得超过 1.8 m",
      "振动超过 5.5 mm/s 或温度超过 82°C 时立即升级停机",
    ],
  },
  "ALT-0823-C": {
    id: "ALT-0823-C",
    label: "方案 C",
    title: "继续满功率运行并增强监测",
    description: "维持当前功率，每 5 分钟采样一次并仅在达到 Critical 阈值后停机。",
    workOrderIssue: "方案 C · WT-023 满功率增强监测",
    workOrderDescription: "执行远程增强监测、阈值复核与趋势留证；达到 Critical 阈值时立即停机。",
    assignedTeam: "SCADA 远程值班组",
    estimatedDurationHours: 24,
    taskTitles: [
      "确认满功率运行边界并记录润滑状态基线",
      "将三向振动采样提升至每 5 分钟并采集频谱",
      "复核主轴承温度阈值与自动告警",
      "复核历史内窥镜证据与在线滚道缺陷趋势",
      "上传增强监测趋势、告警记录和继续运行结论",
    ],
    requiredTools: ["SCADA 远程诊断台", "CMS 在线监测"],
    ppeRequirements: [],
    safetyProcedures: [
      "振动达到 5.5 mm/s 或温度达到 82°C 时自动触发停机升级",
      "远程值班每小时复核一次趋势和告警链路",
      "监测链路中断时不得继续满功率运行",
    ],
  },
};

export const isServerWorkflowAlternativeId = (value) =>
  typeof value === "string" && SERVER_WORKFLOW_ALTERNATIVE_IDS.includes(value);

export const getServerWorkflowAlternativePlan = (value) =>
  isServerWorkflowAlternativeId(value) ? serverWorkflowAlternativePlans[value] : null;
