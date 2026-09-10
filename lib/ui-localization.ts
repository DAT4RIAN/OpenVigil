const statusLabels: Readonly<Record<string, string>> = {
  active: "活动",
  acknowledged: "已确认",
  analyzing: "分析中",
  approved: "已批准",
  available: "可用",
  cataloged: "已编目",
  closed: "已关闭",
  completed: "已完成",
  connected: "已连接",
  critical: "严重",
  degraded: "退化",
  detected: "已发现",
  diagnosed: "已诊断",
  disconnected: "未连接",
  draft: "草案",
  executing: "执行中",
  failed: "失败",
  fallback: "降级快照",
  good: "良好",
  healthy: "健康",
  idle: "空闲",
  info: "信息",
  investigating: "调查中",
  "in-progress": "进行中",
  low: "低",
  major: "重要",
  maintenance: "维护中",
  medium: "中",
  minor: "次要",
  monitoring: "监测中",
  normal: "正常",
  "not-required": "无需分析",
  offline: "离线",
  online: "在线",
  pending: "待处理",
  "pending-approval": "等待审批",
  queued: "排队中",
  ready: "就绪",
  rejected: "已拒绝",
  "revision-requested": "要求修订",
  reviewing: "审核中",
  resolved: "已解决",
  running: "运行中",
  scheduled: "已排程",
  shortage: "库存不足",
  suitable: "适合",
  suppressed: "已抑制",
  thinking: "分析中",
  "under-review": "审核中",
  unavailable: "不可用",
  uncertain: "不确定",
  verified: "已验证",
  vectorized: "已索引",
  waiting: "等待中",
  warning: "警告",
  watch: "关注",
  working: "工作中",
};

const severityLabels: Readonly<Record<string, string>> = {
  critical: "严重",
  high: "高",
  major: "重要",
  medium: "中",
  minor: "次要",
  low: "低",
  warning: "警告",
  info: "信息",
};

const missionTitles: Readonly<Record<string, string>> = {
  "Main Bearing Anomaly": "主轴承异常",
  "Gearbox Particle Count Surge": "齿轮箱颗粒计数激增",
  "Converter Cooling Flow Loss": "变流器冷却流量下降",
  "Blade 3 Pitch Tracking Drift": "3 号叶片变桨跟踪偏差",
  "Grid Voltage Dip Correlation": "电网电压跌落关联分析",
  "SCADA Communication Latency": "SCADA 通信延迟",
  "Nacelle Cooling Cycling Review": "机舱冷却循环复核",
  "Yaw Motor Current Imbalance": "偏航电机电流不平衡",
  "Tower Natural Frequency Shift": "塔筒固有频率偏移",
  "Transformer Dissolved Gas Trend": "变压器溶解气体趋势",
  "Lightning Protection Inspection": "雷电防护检查",
  "Automatic Lubrication Pressure Drop": "自动润滑压力下降",
};

const subsystemLabels: Readonly<Record<string, string>> = {
  blades: "叶片",
  hub: "轮毂",
  "main-shaft": "主轴",
  "main-bearing": "主轴承",
  gearbox: "齿轮箱",
  generator: "发电机",
  converter: "变流器",
  yaw: "偏航系统",
  pitch: "变桨系统",
  tower: "塔筒",
  foundation: "基础",
  electrical: "电气系统",
  scada: "SCADA 系统",
};

const metricLabels: Readonly<Record<string, string>> = {
  "wind-speed": "风速",
  "wind-direction": "风向",
  "rotor-speed": "叶轮转速",
  "generator-speed": "发电机转速",
  "active-power": "有功功率",
  "reactive-power": "无功功率",
  "generator-temperature": "发电机温度",
  "gearbox-oil-temperature": "齿轮箱油温",
  "main-bearing-temperature": "主轴承温度",
  "main-bearing-vibration-rms": "主轴承振动 RMS",
  "nacelle-temperature": "机舱温度",
  "tower-acceleration": "塔筒加速度",
  "blade-pitch": "叶片桨距角",
  "yaw-error": "偏航误差",
  "grid-voltage": "电网电压",
  "grid-frequency": "电网频率",
  "anomaly-score": "AI 异常分数",
};

const evidenceTypeLabels: Readonly<Record<string, string>> = {
  "scada-signal": "SCADA 信号",
  "vibration-spectrum": "振动频谱",
  "model-output": "模型输出",
  "historical-case": "历史案例",
  "maintenance-record": "维护记录",
  "knowledge-document": "知识文档",
  "weather-forecast": "天气预报",
  "resource-check": "资源核验",
};

export const localizedStatusLabel = (value: string): string =>
  statusLabels[value.toLowerCase().replaceAll("_", "-")] ?? value;

export const localizedSeverityLabel = (value: string): string =>
  severityLabels[value.toLowerCase()] ?? localizedStatusLabel(value);

export const localizedMissionTitle = (value: string): string => missionTitles[value] ?? value;

export const localizedSubsystemLabel = (value: string): string =>
  subsystemLabels[value.toLowerCase()] ?? value.replaceAll("-", " ");

export const localizedMetricLabel = (metric: string, fallback?: string): string =>
  metricLabels[metric.toLowerCase()] ?? fallback ?? metric;

export const localizedEvidenceType = (value: string): string =>
  evidenceTypeLabels[value.toLowerCase()] ?? value.replaceAll("-", " ");
