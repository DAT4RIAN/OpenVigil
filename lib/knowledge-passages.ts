import type { ServerWorkflowSnapshot } from "./server-workflow-contract";

export interface KnowledgePassage {
  readonly id: string;
  readonly documentId: string;
  readonly page: number;
  readonly section: string;
  readonly body: string;
  readonly contentHash: string;
  readonly tokenCount: number;
  readonly turbineId: string | null;
  readonly missionId: string | null;
  readonly createdAt: string;
  readonly updatedAt: string;
}

interface PassageInput {
  readonly id: string;
  readonly documentId: string;
  readonly page: number;
  readonly section: string;
  readonly body: string;
  readonly turbineId?: string | null;
  readonly missionId?: string | null;
  readonly updatedAt: string;
}

const DATASET_CREATED_AT = "2026-08-13T02:14:28+08:00";

/** A stable content identity for deterministic fixture seeding (not an embedding). */
export function stablePassageContentHash(body: string): string {
  let hash = 0x811c9dc5;
  for (const byte of new TextEncoder().encode(body.normalize("NFKC"))) {
    hash ^= byte;
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return `fnv1a32:${hash.toString(16).padStart(8, "0")}`;
}

export function estimatePassageTokenCount(body: string): number {
  return Math.max(1, Math.ceil(new TextEncoder().encode(body).length / 4));
}

function definePassage(input: PassageInput): KnowledgePassage {
  return Object.freeze({
    ...input,
    contentHash: stablePassageContentHash(input.body),
    tokenCount: estimatePassageTokenCount(input.body),
    turbineId: input.turbineId ?? null,
    missionId: input.missionId ?? null,
    createdAt: DATASET_CREATED_AT,
  });
}

/**
 * Page-addressable source excerpts used by both the D1 seed and the explicit
 * no-binding fallback. Every assistant citation is cut from one of these bodies.
 */
export const knowledgePassages: readonly KnowledgePassage[] = [
  definePassage({
    id: "KBP-SCADA-023-012",
    documentId: "KB-SCADA-REPORT-023",
    page: 12,
    section: "24 小时联合趋势",
    body: "WT-023 主轴承振动 RMS 在 24 小时内由 3.79 mm/s 升至 4.81 mm/s，增幅 27%。同工况归一化温度比 30 日基线高 8.4°C，两个趋势在告警前持续同向上升。",
    turbineId: "WT-023",
    missionId: "MISSION-2026-0823",
    updatedAt: "2026-08-13T02:14:28+08:00",
  }),
  definePassage({
    id: "KBP-SCADA-023-014",
    documentId: "KB-SCADA-REPORT-023",
    page: 14,
    section: "异常评分与包络谱",
    body: "联合异常模型评分为 0.86；主轴承 BPFO 频带能量比基线增加 19%。该段证据用于交叉验证振动趋势，不单独作为根因结论。",
    turbineId: "WT-023",
    missionId: "MISSION-2026-0823",
    updatedAt: "2026-08-13T02:14:28+08:00",
  }),
  definePassage({
    id: "KBP-CASE-2019-017-007",
    documentId: "KB-CASE-2019-017",
    page: 7,
    section: "相似症状与确认结果",
    body: "案例 2019-017 同时出现振动 RMS 增长 24%、温升 7.9°C 和 BPFO 包络谱增强，检修后确认滚道早期剥落。WT-023 当前特征与该案例的确定性特征相似度为 0.91。",
    turbineId: "WT-023",
    missionId: "MISSION-2026-0823",
    updatedAt: "2026-04-26T16:45:00+08:00",
  }),
  definePassage({
    id: "KBP-MB-PROC-004-009",
    documentId: "KB-MB-PROC-004",
    page: 9,
    section: "联合取证步骤",
    body: "主轴承异常不得依据单点越限直接定性。应依次完成振动复测、温度核验、润滑脂取样和内窥镜检查，并保留测量时间、工况与影像证据。",
    turbineId: null,
    missionId: null,
    updatedAt: "2026-07-02T09:10:00+08:00",
  }),
  definePassage({
    id: "KBP-MB-PROC-004-016",
    documentId: "KB-MB-PROC-004",
    page: 16,
    section: "复测判据",
    body: "复测应在可比风速与功率区间执行。若振动、温升和润滑状态仍共同恶化，应升级停机检查；若指标回落，应记录健康度回写和后续观察周期。",
    turbineId: null,
    missionId: null,
    updatedAt: "2026-07-02T09:10:00+08:00",
  }),
  definePassage({
    id: "KBP-INSPECTION-023-Q2-018",
    documentId: "KB-INSPECTION-023-2026Q2",
    page: 18,
    section: "传动链巡检记录",
    body: "WT-023 二季度巡检未发现可见损伤，但驱动端润滑脂颜色较上次轻微变深。记录建议结合后续振动和温度趋势复核润滑状态。",
    turbineId: "WT-023",
    missionId: "MISSION-2026-0823",
    updatedAt: "2026-06-21T15:40:00+08:00",
  }),
  definePassage({
    id: "KBP-GW165-OM-001-214",
    documentId: "KB-GW165-OM-001",
    page: 214,
    section: "主轴承监测边界",
    body: "GW165 主轴承状态应同时核对振动 RMS、轴承温度和运行工况。达到告警边界后需复测；超过停机边界或伴随特征频带持续增强时，应执行受控停机检查。",
    turbineId: null,
    missionId: null,
    updatedAt: "2026-05-18T14:20:00+08:00",
  }),
  definePassage({
    id: "KBP-ISO-10816-016",
    documentId: "KB-ISO-10816",
    page: 16,
    section: "Vibration evaluation zones",
    body: "Vibration RMS evaluation zones are reference boundaries for rotating machinery. Trending under comparable load is required; one threshold crossing alone does not identify the damaged component.",
    turbineId: null,
    missionId: null,
    updatedAt: "2025-12-12T11:30:00+08:00",
  }),
  definePassage({
    id: "KBP-WO-2025-118-006",
    documentId: "KB-WO-2025-118",
    page: 6,
    section: "处置与复测",
    body: "历史工单 WO-20250718-118 通过润滑脂取样、补脂、排脂检查和同工况振动复测排除了润滑不足。现场任务完成后，健康评分回升并进入 30 日观察。",
    turbineId: "WT-023",
    missionId: "MISSION-2026-0823",
    updatedAt: "2025-07-22T17:05:00+08:00",
  }),
  definePassage({
    id: "KBP-SAFETY-STD-011-021",
    documentId: "KB-SAFETY-STD-011",
    page: 21,
    section: "登塔与能源隔离",
    body: "海上登塔和机舱检查必须确认人员转运窗口、PPE、LOTO 能源隔离与应急撤离条件。风浪或雷电风险不满足限制时不得开始现场任务。",
    turbineId: null,
    missionId: null,
    updatedAt: "2026-06-14T08:40:00+08:00",
  }),
  definePassage({
    id: "KBP-OPS-PROC-002-012",
    documentId: "KB-OPS-PROC-002",
    page: 12,
    section: "任务策划审批",
    body: "高风险维护方案应完成风险评估、天气窗口、班组、CTV、工具和备件确认，并由人工审批后生成可执行工单。审批意见和资源预留需进入审计记录。",
    turbineId: null,
    missionId: null,
    updatedAt: "2026-03-30T13:25:00+08:00",
  }),
  definePassage({
    id: "KBP-GEARBOX-CASE-022-008",
    documentId: "KB-GEARBOX-CASE-022",
    page: 8,
    section: "磨粒与齿面损伤",
    body: "WT-041 齿轮箱铁磁磨粒计数升至基线 2.8 倍，油样复核与啮合频带变化共同指向齿面点蚀。案例要求在停机阈值前安排内窥镜检查。",
    turbineId: "WT-041",
    missionId: "MISSION-2026-0824",
    updatedAt: "2026-01-19T10:15:00+08:00",
  }),
] as const;

/**
 * Ownership boundary for the deterministic passage fixture.
 *
 * Active IDs are derived from the current corpus, while retired IDs must be
 * added explicitly when a fixture passage is renamed or removed. Runtime
 * synchronization may update/delete only IDs recorded here; workflow overlays
 * and user-authored passages therefore remain outside the fixture lifecycle.
 */
export const knowledgePassageFixtureManifest = Object.freeze({
  version: "2026-08-13.1",
  activePassageIds: Object.freeze(knowledgePassages.map(({ id }) => id)),
  retiredPassageIds: Object.freeze(["KBP-MB-PROC-004-008"]),
});

export function workflowKnowledgePassage(
  snapshot: ServerWorkflowSnapshot,
): KnowledgePassage | null {
  if (!snapshot.knowledgeCaseId) return null;
  const knowledgeEvent = [...snapshot.auditEvents]
    .reverse()
    .find((event) => event.kind === "knowledge");
  return definePassage({
    id: `KBP-${snapshot.knowledgeCaseId}-006`,
    documentId: snapshot.knowledgeCaseId,
    page: 6,
    section: "闭环验证与健康回写",
    body: `WT-023 闭环案例记录了人工审批、五项现场任务和复测验证。任务完成后，机组健康度回写为 ${snapshot.health.turbineScore}，主轴承健康度由 63 回升至 ${snapshot.health.mainBearingScore}；审计事件与知识案例均持久化。`,
    turbineId: snapshot.turbineId,
    missionId: snapshot.mission.id,
    updatedAt: knowledgeEvent?.timestamp ?? snapshot.updatedAt,
  });
}
