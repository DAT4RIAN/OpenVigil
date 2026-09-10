import { agents } from "./agent-data";
import { agentDisplayName } from "./agent-control-meta";
import { turbines } from "./farm-data";
import { healthAssessments } from "./health-data";
import { evidenceItems, missions } from "./operations-data";
import type { DecisionStatus, MissionStatus, RiskLevel, WorkOrderStatus } from "./types";

export const diagnosisStatuses = [
  "triage",
  "monitoring",
  "analyzed",
  "awaiting-review",
  "revision-needed",
  "rejected",
  "scheduled",
  "in-progress",
  "closed",
] as const;

export type DiagnosisStatus = (typeof diagnosisStatuses)[number];

export const diagnosisRiskLevels = ["critical", "high", "medium", "low"] as const;

export const diagnosisSortModes = [
  "priority-desc",
  "updated-desc",
  "confidence-desc",
  "turbine-asc",
] as const;

export type DiagnosisSortMode = (typeof diagnosisSortModes)[number];

export interface DiagnosisSignal {
  readonly id: string;
  readonly label: string;
  readonly value: number;
  readonly baseline: number;
  readonly unit: string;
  readonly deltaPercent: number;
  readonly abnormal: boolean;
}

export interface DiagnosisAnomalyIntake {
  readonly source: "scada-anomaly" | "alarm-correlation" | "scheduled-health-scan";
  readonly detectedAt: string;
  readonly anomalyScore: number;
  readonly threshold: number;
  readonly summary: string;
  readonly signals: readonly DiagnosisSignal[];
}

export interface DiagnosisCandidate {
  readonly id: string;
  readonly faultMode: string;
  readonly subsystem: string;
  readonly probabilityPercent: number;
  readonly confidencePercent: number;
  readonly supportingEvidenceIds: readonly string[];
  readonly supportingSummary: readonly string[];
  readonly counterEvidence: readonly string[];
  readonly recommendedNextStep: string;
}

export interface DiagnosisCitation {
  readonly id: string;
  readonly title: string;
  readonly sourceLabel: string;
  readonly sourceType: string;
  readonly observedAt: string;
  readonly summary: string;
  readonly href: string;
  readonly deepLink: true;
}

export interface DiagnosisToolResult {
  readonly tool: string;
  readonly result: string;
}

export interface DiagnosisAgentStep {
  readonly id: string;
  readonly sequence: number;
  readonly agentId: string;
  readonly agentName: string;
  readonly role: string;
  readonly status: "complete" | "waiting-human" | "monitoring";
  readonly publicOutput: string;
  readonly evidenceIds: readonly string[];
  readonly toolResults: readonly DiagnosisToolResult[];
  readonly completedAt: string | null;
}

export interface DiagnosisGate {
  readonly state: "locked" | "review-required" | "authorized" | "active" | "verified";
  readonly humanReviewRequired: boolean;
  readonly title: string;
  readonly explanation: string;
  readonly allowedActions: readonly string[];
  readonly blockedActions: readonly string[];
  readonly decisionStatus: DecisionStatus | null;
  readonly workOrderStatus: WorkOrderStatus | null;
}

export interface DiagnosisRecord {
  readonly id: string;
  readonly turbineId: string;
  readonly turbineStatus: string;
  readonly healthScore: number;
  readonly risk: RiskLevel;
  readonly status: DiagnosisStatus;
  readonly headline: string;
  readonly overallConfidencePercent: number;
  readonly missionId: string | null;
  readonly activeAlarmCount: number;
  readonly updatedAt: string;
  readonly anomaly: DiagnosisAnomalyIntake;
  readonly candidates: readonly DiagnosisCandidate[];
  readonly citations: readonly DiagnosisCitation[];
  readonly collaboration: readonly DiagnosisAgentStep[];
  readonly gate: DiagnosisGate;
}

export interface DiagnosisWorkflowOverlay {
  readonly missionStatus: MissionStatus;
  readonly decisionStatus: DecisionStatus;
  readonly workOrderStatus: WorkOrderStatus;
}

export const diagnosisModelMeta = Object.freeze({
  mode: "deterministic-diagnostic-fixture",
  deterministic: true,
  readOnly: true,
  realInference: false,
  publicTraceOnly: true,
  snapshotAt: "2026-08-13T10:30:00+08:00",
  notice:
    "诊断结果由固定 SCADA、告警、健康与知识证据生成，仅供产品演示；不会调用真实模型或下发控制指令。",
});

const canonicalWorkflow: DiagnosisWorkflowOverlay = {
  missionStatus: "under-review",
  decisionStatus: "under-review",
  workOrderStatus: "draft",
};

const riskWeight: Readonly<Record<RiskLevel, number>> = {
  critical: 4,
  high: 3,
  medium: 2,
  low: 1,
};

const agentName = (id: string): string => {
  const agent = agents.find((item) => item.id === id);
  return agentDisplayName(id, agent?.shortName ?? id);
};

const sourceHref = (sourceId: string | null): string => {
  if (!sourceId) return "/missions/MISSION-2026-0823#evidence";
  if (sourceId.startsWith("SCADA-")) {
    const metric = sourceId.replace("SCADA-WT-023-", "");
    return `/scada?turbineId=WT-023&metric=${metric}`;
  }
  if (sourceId.startsWith("KB-")) return `/knowledge?document=${sourceId}`;
  if (sourceId.startsWith("WW-")) return `/resources?weatherWindow=${sourceId}`;
  if (sourceId.startsWith("MODEL-")) return "/predictive-maintenance?turbineId=WT-023";
  return `/missions/MISSION-2026-0823#evidence`;
};

const featuredCitationIds = [
  "EV-023-VIB-001",
  "EV-023-TEMP-002",
  "EV-023-SPECTRUM-005",
  "EV-023-HISTORY-006",
  "EV-023-MAINT-007",
  "EV-023-MANUAL-008",
  "EV-023-RUL-011",
] as const;

const featuredCitations: readonly DiagnosisCitation[] = featuredCitationIds.map((id) => {
  const evidence = evidenceItems.find((item) => item.id === id)!;
  return Object.freeze({
    id: evidence.id,
    title: evidence.title,
    sourceLabel: evidence.sourceLabel,
    sourceType: evidence.type,
    observedAt: evidence.observedAt,
    summary: evidence.summary,
    href: sourceHref(evidence.sourceId),
    deepLink: true as const,
  });
});

const featuredCandidates: readonly DiagnosisCandidate[] = [
  {
    id: "DX-023-CANDIDATE-01",
    faultMode: "主轴承外圈早期退化",
    subsystem: "主轴承",
    probabilityPercent: 87,
    confidencePercent: 89,
    supportingEvidenceIds: [
      "EV-023-VIB-001",
      "EV-023-TEMP-002",
      "EV-023-SPECTRUM-005",
      "EV-023-HISTORY-006",
    ],
    supportingSummary: [
      "振动 RMS 24 小时上升 27%，并持续跨越 Warning 阈值",
      "BPFO 近似频率附近能量增加 19%，出现转频调制边带",
      "温度较同工况基线高 8.4°C，历史案例相似度 0.91",
    ],
    counterEvidence: ["尚未出现持续功率损失", "当前没有冲击幅值跨越紧急停机阈值"],
    recommendedNextStep: "保持门禁锁定；人工批准后在 72 小时内执行润滑、频谱与内窥镜联合检查。",
  },
  {
    id: "DX-023-CANDIDATE-02",
    faultMode: "润滑状态劣化或污染",
    subsystem: "主轴承润滑系统",
    probabilityPercent: 9,
    confidencePercent: 72,
    supportingEvidenceIds: ["EV-023-TEMP-002", "EV-023-MAINT-007"],
    supportingSummary: ["Q2 巡检记录润滑脂颜色变深", "温升可由摩擦或润滑膜异常解释"],
    counterEvidence: ["单纯润滑异常不足以解释 BPFO 特征边带", "尚无润滑脂实验室颗粒度结果"],
    recommendedNextStep: "现场检查时同步采集润滑脂样本，避免在证据不足时直接更换轴承。",
  },
  {
    id: "DX-023-CANDIDATE-03",
    faultMode: "转子不平衡或对中偏差",
    subsystem: "传动链",
    probabilityPercent: 4,
    confidencePercent: 64,
    supportingEvidenceIds: ["EV-023-VIB-001"],
    supportingSummary: ["振动与功率波动存在同步偏离"],
    counterEvidence: ["频谱主特征更接近轴承外圈缺陷", "没有稳定的 1× 转频主峰占优证据"],
    recommendedNextStep: "保留为现场复核项，不作为当前处置方案的主假设。",
  },
];

const featuredCollaboration: readonly DiagnosisAgentStep[] = [
  {
    id: "DX-023-STEP-01",
    sequence: 1,
    agentId: "agent-scada-analysis",
    agentName: agentName("agent-scada-analysis"),
    role: "异常接入与信号相关",
    status: "complete",
    publicOutput: "确认振动、温度与功率残差在同一时间窗联合偏离，数据质量良好。",
    evidenceIds: ["EV-023-VIB-001", "EV-023-TEMP-002"],
    toolResults: [
      { tool: "query_scada", result: "读取 24H 窗口；44 个连续上升采样点" },
      { tool: "get_turbine_status", result: "WT-023 在线，当前处于告警状态" },
    ],
    completedAt: "2026-08-13T02:14:12+08:00",
  },
  {
    id: "DX-023-STEP-02",
    sequence: 2,
    agentId: "agent-vibration-diagnosis",
    agentName: agentName("agent-vibration-diagnosis"),
    role: "频谱特征诊断",
    status: "complete",
    publicOutput: "提取 BPFO 近似频率与转频边带，主候选指向外圈早期退化。",
    evidenceIds: ["EV-023-SPECTRUM-005"],
    toolResults: [{ tool: "query_vibration", result: "BPFO 频带能量较基线增长 19%" }],
    completedAt: "2026-08-13T02:14:27+08:00",
  },
  {
    id: "DX-023-STEP-03",
    sequence: 3,
    agentId: "agent-knowledge",
    agentName: agentName("agent-knowledge"),
    role: "案例与手册检索",
    status: "complete",
    publicOutput: "检索到 12 个历史案例与厂家 72 小时复检要求，最高案例相似度 0.91。",
    evidenceIds: ["EV-023-HISTORY-006", "EV-023-MANUAL-008"],
    toolResults: [
      { tool: "query_similar_failures", result: "12 个案例；最高相似度 0.91" },
      { tool: "query_manual", result: "命中 GW165 运维手册 §8.4.3" },
    ],
    completedAt: "2026-08-13T02:14:22+08:00",
  },
  {
    id: "DX-023-STEP-04",
    sequence: 4,
    agentId: "agent-failure-diagnosis",
    agentName: agentName("agent-failure-diagnosis"),
    role: "证据融合与差分诊断",
    status: "complete",
    publicOutput: "形成 3 个候选故障模式；主轴承外圈早期退化概率 87%，仍需现场取证确认。",
    evidenceIds: ["EV-023-VIB-001", "EV-023-TEMP-002", "EV-023-SPECTRUM-005", "EV-023-HISTORY-006"],
    toolResults: [
      { tool: "calculate_health_score", result: "主轴承健康评分 63 / 100" },
      { tool: "predict_rul", result: "RUL 点估计 47 天；90% 区间 31–66 天" },
    ],
    completedAt: "2026-08-13T02:14:41+08:00",
  },
  {
    id: "DX-023-STEP-05",
    sequence: 5,
    agentId: "agent-safety-review",
    agentName: agentName("agent-safety-review"),
    role: "风险复核与 HITL 门禁",
    status: "waiting-human",
    publicOutput: "高风险降载与海上检查需人工授权；当前只允许查看证据和现有 Mission。",
    evidenceIds: ["EV-023-MANUAL-008", "EV-023-RUL-011"],
    toolResults: [{ tool: "create_decision", result: "DECISION-2026-0823 已提交人工复核" }],
    completedAt: null,
  },
];

const defaultGate = (risk: RiskLevel): DiagnosisGate => ({
  state: risk === "critical" || risk === "high" ? "review-required" : "locked",
  humanReviewRequired: risk === "critical" || risk === "high",
  title: risk === "critical" || risk === "high" ? "人工复核后方可处置" : "观察模式 · 无控制权限",
  explanation:
    risk === "critical" || risk === "high"
      ? "当前记录仅形成结构化诊断，任何降载、停机或现场作业都需要人工复核。"
      : "当前仅建议趋势跟踪；诊断页面不会自动创建任务或向机组下发控制。",
  allowedActions: ["查看证据深链", "打开资产详情", "查看既有 Mission"],
  blockedActions: ["自动降载或停机", "自动创建或执行工单"],
  decisionStatus: null,
  workOrderStatus: null,
});

function featuredGate(workflow: DiagnosisWorkflowOverlay): DiagnosisGate {
  if (workflow.missionStatus === "completed" || workflow.workOrderStatus === "completed") {
    return {
      state: "verified",
      humanReviewRequired: true,
      title: "现场结果已验证并闭环",
      explanation: "人工授权、现场检查和复测记录已形成完整审计链。",
      allowedActions: ["查看闭环证据", "复用知识案例", "继续趋势监测"],
      blockedActions: ["无新审批记录时再次下发控制"],
      decisionStatus: workflow.decisionStatus,
      workOrderStatus: workflow.workOrderStatus,
    };
  }
  if (workflow.workOrderStatus === "in-progress") {
    return {
      state: "active",
      humanReviewRequired: true,
      title: "人工授权后的工单受控进行中",
      explanation: "仅允许按既有工单任务与安全边界作业，超阈值必须再次升级。",
      allowedActions: ["回写现场证据", "更新工单任务", "触发安全升级"],
      blockedActions: ["扩大作业范围", "绕过复测直接闭环"],
      decisionStatus: workflow.decisionStatus,
      workOrderStatus: workflow.workOrderStatus,
    };
  }
  if (workflow.workOrderStatus === "scheduled" || workflow.decisionStatus === "approved") {
    return {
      state: "authorized",
      humanReviewRequired: true,
      title: "人工授权已记录 · 等待安全窗口",
      explanation: "授权范围仅覆盖方案 B 与 WO-20260823-017，开始前仍需现场班组确认。",
      allowedActions: ["确认天气与资源", "按排程打开现有工单"],
      blockedActions: ["改变授权方案", "绕过开工检查"],
      decisionStatus: workflow.decisionStatus,
      workOrderStatus: workflow.workOrderStatus,
    };
  }
  if (workflow.decisionStatus === "revision-requested") {
    return {
      state: "locked",
      humanReviewRequired: true,
      title: "方案需修订 · 门禁保持锁定",
      explanation: "审核人要求补充证据或调整处置边界，草稿工单没有执行权限。",
      allowedActions: ["补充证据", "修订处置方案", "重新提交复核"],
      blockedActions: ["自动降载或停机", "执行草稿工单"],
      decisionStatus: workflow.decisionStatus,
      workOrderStatus: workflow.workOrderStatus,
    };
  }
  if (workflow.decisionStatus === "rejected") {
    return {
      state: "locked",
      humanReviewRequired: true,
      title: "方案被拒绝 · 门禁保持锁定",
      explanation: "当前方案不可用于处置，需生成替代方案并重新进入人工复核。",
      allowedActions: ["查看拒绝理由", "生成替代方案", "补充诊断证据"],
      blockedActions: ["自动降载或停机", "执行关联草稿工单"],
      decisionStatus: workflow.decisionStatus,
      workOrderStatus: workflow.workOrderStatus,
    };
  }
  return {
    state: "locked",
    humanReviewRequired: true,
    title: "HITL 门禁锁定 · 人工复核中",
    explanation: "DECISION-2026-0823 仍在人工复核；WO-20260823-017 为草稿，不具备执行权限。",
    allowedActions: ["查看证据深链", "打开现有 Mission", "提交人工复核意见"],
    blockedActions: ["自动降载或停机", "排程或执行草稿工单"],
    decisionStatus: workflow.decisionStatus,
    workOrderStatus: workflow.workOrderStatus,
  };
}

function featuredStatus(workflow: DiagnosisWorkflowOverlay): DiagnosisStatus {
  if (workflow.missionStatus === "completed" || workflow.workOrderStatus === "completed") {
    return "closed";
  }
  if (workflow.workOrderStatus === "in-progress") return "in-progress";
  if (workflow.workOrderStatus === "scheduled" || workflow.decisionStatus === "approved") {
    return "scheduled";
  }
  if (workflow.decisionStatus === "revision-requested") return "revision-needed";
  if (workflow.decisionStatus === "rejected") return "rejected";
  return "awaiting-review";
}

function genericCandidates(number: number, risk: RiskLevel): readonly DiagnosisCandidate[] {
  const modes = [
    ["传感器漂移或测点偏置", "监测系统"],
    ["润滑状态轻微偏离", "传动链"],
    ["环境载荷引起的短时波动", "整机"],
  ] as const;
  const topProbability =
    risk === "critical" ? 74 : risk === "high" ? 66 : risk === "medium" ? 57 : 48;
  const adjustedTop = Math.min(79, topProbability + (number % 5));
  const second = Math.round((100 - adjustedTop) * 0.62);
  const probabilities = [adjustedTop, second, 100 - adjustedTop - second];

  return modes.map(([faultMode, subsystem], index) => ({
    id: `DX-${String(number).padStart(3, "0")}-CANDIDATE-0${index + 1}`,
    faultMode,
    subsystem,
    probabilityPercent: probabilities[index],
    confidencePercent: Math.max(52, 82 - index * 11 - (number % 4)),
    supportingEvidenceIds: [`DX-EV-${String(number).padStart(3, "0")}-HEALTH`],
    supportingSummary: [
      index === 0
        ? "健康评分与异常分数存在可重复的固定偏离"
        : "该候选能解释部分趋势，但证据覆盖度较低",
    ],
    counterEvidence: [
      index === 0 ? "尚未获得现场复测证据" : "当前主要信号与该候选的典型模式不完全一致",
    ],
    recommendedNextStep:
      risk === "critical" || risk === "high"
        ? "由值班工程师复核相关信号与告警，再决定是否创建处置 Mission。"
        : "保持只读趋势监测，在异常分数跨越 0.65 时升级人工分诊。",
  }));
}

function genericCitations(
  turbineId: string,
  finding: string,
  assessedAt: string,
  activeAlarmCount: number,
): readonly DiagnosisCitation[] {
  const citations: DiagnosisCitation[] = [
    {
      id: `DX-EV-${turbineId.slice(3)}-HEALTH`,
      title: `${turbineId} 健康评分快照`,
      sourceLabel: "WindOps Fleet Health",
      sourceType: "health-assessment",
      observedAt: assessedAt,
      summary: finding,
      href: `/health?turbineId=${turbineId}`,
      deepLink: true,
    },
    {
      id: `DX-EV-${turbineId.slice(3)}-ASSET`,
      title: `${turbineId} 数字资产上下文`,
      sourceLabel: "WindOps Asset Registry",
      sourceType: "asset-context",
      observedAt: assessedAt,
      summary: "型号、运行状态、健康度与当前 Mission 关联。",
      href: `/turbines/${turbineId}#subsystems`,
      deepLink: true,
    },
  ];
  if (activeAlarmCount > 0) {
    citations.push({
      id: `DX-EV-${turbineId.slice(3)}-ALARMS`,
      title: `${turbineId} 活跃告警上下文`,
      sourceLabel: "WindOps 告警中心",
      sourceType: "alarm-correlation",
      observedAt: assessedAt,
      summary: `${activeAlarmCount} 条活跃告警参与异常接入。`,
      href: `/alarms?turbineId=${turbineId}`,
      deepLink: true,
    });
  }
  return citations;
}

function genericCollaboration(
  turbineId: string,
  risk: RiskLevel,
  missionId: string | null,
): readonly DiagnosisAgentStep[] {
  const suffix = turbineId.slice(3);
  return [
    {
      id: `DX-${suffix}-STEP-01`,
      sequence: 1,
      agentId: "agent-scada-analysis",
      agentName: agentName("agent-scada-analysis"),
      role: "异常接入",
      status: "complete",
      publicOutput: "完成固定窗口的数据质量检查与健康偏离汇总。",
      evidenceIds: [`DX-EV-${suffix}-HEALTH`],
      toolResults: [{ tool: "query_scada", result: "读取演示快照；未发起实时推理" }],
      completedAt: "2026-08-13T10:25:00+08:00",
    },
    {
      id: `DX-${suffix}-STEP-02`,
      sequence: 2,
      agentId: "agent-failure-diagnosis",
      agentName: agentName("agent-failure-diagnosis"),
      role: "候选模式排序",
      status: risk === "critical" || risk === "high" ? "waiting-human" : "monitoring",
      publicOutput:
        risk === "critical" || risk === "high"
          ? "候选模式已结构化排序，等待值班工程师复核。"
          : "未达到自动升级阈值，保持观察并记录固定诊断摘要。",
      evidenceIds: [`DX-EV-${suffix}-HEALTH`],
      toolResults: [
        {
          tool: "query_alarm_history",
          result: missionId ? `已关联既有任务 ${missionId}` : "未发现可关联的既有 Mission",
        },
      ],
      completedAt: risk === "critical" || risk === "high" ? null : "2026-08-13T10:26:00+08:00",
    },
  ];
}

function genericStatus(risk: RiskLevel, missionId: string | null, number: number): DiagnosisStatus {
  if ((risk === "critical" || risk === "high") && missionId) return "awaiting-review";
  if (risk === "critical" || risk === "high") return "triage";
  if (risk === "medium" || number % 7 === 0) return "analyzed";
  return "monitoring";
}

function genericSignals(
  healthScore: number,
  anomalyScore: number,
  activeAlarmCount: number,
): readonly DiagnosisSignal[] {
  return [
    {
      id: "health-score",
      label: "健康评分",
      value: healthScore,
      baseline: 92,
      unit: "/100",
      deltaPercent: Number((((healthScore - 92) / 92) * 100).toFixed(1)),
      abnormal: healthScore < 85,
    },
    {
      id: "anomaly-score",
      label: "异常分数",
      value: anomalyScore,
      baseline: 0.18,
      unit: "score",
      deltaPercent: Number((((anomalyScore - 0.18) / 0.18) * 100).toFixed(1)),
      abnormal: anomalyScore >= 0.65,
    },
    {
      id: "active-alarms",
      label: "活跃告警",
      value: activeAlarmCount,
      baseline: 0,
      unit: "count",
      deltaPercent: activeAlarmCount ? 100 : 0,
      abnormal: activeAlarmCount > 0,
    },
  ];
}

function genericRecord(index: number): DiagnosisRecord {
  const turbine = turbines[index];
  const assessment = healthAssessments[index];
  const number = index + 1;
  const mission = missions.find((item) => item.turbineId === turbine.id) ?? null;
  const status = genericStatus(assessment.riskLevel, mission?.id ?? null, number);

  return {
    id: `DIAG-${turbine.id}-20260813`,
    turbineId: turbine.id,
    turbineStatus: turbine.status,
    healthScore: assessment.healthScore,
    risk: assessment.riskLevel,
    status,
    headline: assessment.primaryFinding,
    overallConfidencePercent: Math.max(58, 86 - (number % 9)),
    missionId: mission?.id ?? null,
    activeAlarmCount: turbine.activeAlarmCount,
    updatedAt: assessment.assessedAt,
    anomaly: {
      source: turbine.activeAlarmCount
        ? "alarm-correlation"
        : assessment.anomalyScore >= 0.65
          ? "scada-anomaly"
          : "scheduled-health-scan",
      detectedAt: assessment.assessedAt,
      anomalyScore: assessment.anomalyScore,
      threshold: 0.65,
      summary: assessment.primaryFinding,
      signals: genericSignals(
        assessment.healthScore,
        assessment.anomalyScore,
        turbine.activeAlarmCount,
      ),
    },
    candidates: genericCandidates(number, assessment.riskLevel),
    citations: genericCitations(
      turbine.id,
      assessment.primaryFinding,
      assessment.assessedAt,
      turbine.activeAlarmCount,
    ),
    collaboration: genericCollaboration(turbine.id, assessment.riskLevel, mission?.id ?? null),
    gate: defaultGate(assessment.riskLevel),
  };
}

const featuredSignals: readonly DiagnosisSignal[] = [
  {
    id: "main-bearing-vibration-rms",
    label: "主轴承振动 RMS",
    value: 4.81,
    baseline: 3.79,
    unit: "mm/s",
    deltaPercent: 27,
    abnormal: true,
  },
  {
    id: "main-bearing-temperature",
    label: "主轴承温度",
    value: 76.4,
    baseline: 68,
    unit: "°C",
    deltaPercent: 12.4,
    abnormal: true,
  },
  {
    id: "bpfo-band-energy",
    label: "BPFO 频带能量",
    value: 19,
    baseline: 0,
    unit: "% 超出基线",
    deltaPercent: 19,
    abnormal: true,
  },
];

function featuredRecord(workflow: DiagnosisWorkflowOverlay): DiagnosisRecord {
  const turbine = turbines[22];
  return {
    id: "DIAG-WT-023-20260813",
    turbineId: turbine.id,
    turbineStatus: turbine.status,
    healthScore: turbine.healthScore,
    risk: "high",
    status: featuredStatus(workflow),
    headline: "主轴承振动、温度与频谱联合异常",
    overallConfidencePercent: 89,
    missionId: "MISSION-2026-0823",
    activeAlarmCount: turbine.activeAlarmCount,
    updatedAt: "2026-08-13T10:30:00+08:00",
    anomaly: {
      source: "scada-anomaly",
      detectedAt: "2026-08-13T02:14:03+08:00",
      anomalyScore: 0.86,
      threshold: 0.65,
      summary: "24 小时窗口内，主轴承振动 RMS 上升 27%，温度较同工况基线高 8.4°C。",
      signals: featuredSignals,
    },
    candidates: featuredCandidates,
    citations: featuredCitations,
    collaboration: featuredCollaboration.map((step) =>
      step.id === "DX-023-STEP-05"
        ? {
            ...step,
            status:
              workflow.decisionStatus === "approved" ||
              workflow.workOrderStatus === "scheduled" ||
              workflow.workOrderStatus === "in-progress" ||
              workflow.workOrderStatus === "completed"
                ? ("complete" as const)
                : ("waiting-human" as const),
            publicOutput:
              workflow.decisionStatus === "under-review"
                ? "高风险降载与海上检查仍需人工授权；当前只允许查看证据和现有 Mission。"
                : step.publicOutput,
            completedAt:
              workflow.decisionStatus === "approved" ? "2026-08-13T09:02:11+08:00" : null,
          }
        : step,
    ),
    gate: featuredGate(workflow),
  };
}

export function createDiagnosisRecords(
  workflow: DiagnosisWorkflowOverlay = canonicalWorkflow,
): readonly DiagnosisRecord[] {
  return turbines.map((_, index) =>
    index === 22 ? featuredRecord(workflow) : genericRecord(index),
  );
}

export const diagnosisRecords = createDiagnosisRecords();

export function sortDiagnosisRecords(
  records: readonly DiagnosisRecord[],
  sort: DiagnosisSortMode,
): DiagnosisRecord[] {
  return [...records].sort((left, right) => {
    if (sort === "turbine-asc") return left.turbineId.localeCompare(right.turbineId);
    if (sort === "updated-desc") {
      return (
        right.updatedAt.localeCompare(left.updatedAt) ||
        left.turbineId.localeCompare(right.turbineId)
      );
    }
    if (sort === "confidence-desc") {
      return (
        right.overallConfidencePercent - left.overallConfidencePercent ||
        left.turbineId.localeCompare(right.turbineId)
      );
    }
    return (
      riskWeight[right.risk] - riskWeight[left.risk] ||
      right.anomaly.anomalyScore - left.anomaly.anomalyScore ||
      left.turbineId.localeCompare(right.turbineId)
    );
  });
}
