import { failureCases } from "./archive-data";
import { knowledgeDocuments } from "./knowledge-data";
import { evidenceItems, featuredMission } from "./operations-data";
import type { ServerWorkflowSnapshot } from "./server-workflow-contract";
import type { FailureCase, KnowledgeDocument } from "./types";

export const DEFAULT_KNOWLEDGE_QUESTION = "WT-023为什么被判断为主轴承退化？";

export interface SourceCitation {
  readonly docId: string;
  readonly title: string;
  readonly page: number;
  readonly summary: string;
  readonly documentType: KnowledgeDocument["type"];
  readonly href: string;
}

export interface KnowledgeFinding {
  readonly label: string;
  readonly value: string;
  readonly interpretation: string;
  readonly evidenceIds: readonly string[];
}

export interface KnowledgeAssistantAnswer {
  readonly responseId: string;
  readonly question: string;
  readonly scope: {
    readonly turbineId: string;
    readonly missionId: string;
  };
  readonly answer: {
    readonly headline: string;
    readonly summary: string;
    readonly findings: readonly KnowledgeFinding[];
    readonly conclusion: string;
    readonly confidencePercent: number;
  };
  readonly citations: readonly SourceCitation[];
  readonly retrieval: {
    readonly mode: "deterministic-keyword-demo";
    readonly queryTerms: readonly string[];
    readonly candidateCount: number;
    readonly retrievedCount: number;
    readonly evidenceIds: readonly string[];
    readonly supportingFailureCaseIds: readonly string[];
  };
  readonly generatedAt: string;
  readonly disclaimer: string;
}

interface RankedDocument {
  readonly document: KnowledgeDocument;
  readonly score: number;
}

const SNAPSHOT_AT = "2026-08-13T10:24:00+08:00";
const RELATED_EVIDENCE_IDS = [
  "EV-023-VIB-001",
  "EV-023-TEMP-002",
  "EV-023-ANOMALY-004",
  "EV-023-SPECTRUM-005",
  "EV-023-HISTORY-006",
  "EV-023-MAINT-007",
] as const;

const domainTerms = [
  "wt-023",
  "主轴承",
  "退化",
  "振动",
  "温度",
  "温升",
  "bpfo",
  "包络谱",
  "scada",
  "历史案例",
  "润滑",
] as const;

const pageByDocumentId: Readonly<Record<string, number>> = {
  "KB-SCADA-REPORT-023": 12,
  "KB-CASE-2019-017": 7,
  "KB-MB-PROC-004": 9,
  "KB-INSPECTION-023-2026Q2": 18,
  "KB-GW165-OM-001": 214,
};

const curatedBoostByDocumentId: Readonly<Record<string, number>> = {
  "KB-SCADA-REPORT-023": 24,
  "KB-CASE-2019-017": 22,
  "KB-MB-PROC-004": 18,
  "KB-INSPECTION-023-2026Q2": 16,
  "KB-GW165-OM-001": 12,
};

const normalize = (value: string): string => value.trim().toLocaleLowerCase("zh-CN");

export function extractKnowledgeQueryTerms(question: string): readonly string[] {
  const normalized = normalize(question);
  const latinTerms = normalized.match(/[a-z]+(?:-[a-z0-9]+)*|\d+(?:\.\d+)?/g) ?? [];
  const matchedDomainTerms = domainTerms.filter((term) => normalized.includes(term));
  return [...new Set([...matchedDomainTerms, ...latinTerms])].sort();
}

export function rankKnowledgeDocuments(
  question: string,
  turbineId = "WT-023",
  missionId = featuredMission.id,
  documents: readonly KnowledgeDocument[] = knowledgeDocuments,
  preferredDocumentId: string | null = null,
): readonly RankedDocument[] {
  const queryTerms = extractKnowledgeQueryTerms(question);
  const normalizedTurbineId = turbineId.toUpperCase();

  return documents
    .map((document) => {
      const searchable = normalize(
        [
          document.id,
          document.title,
          document.type,
          document.equipment,
          document.manufacturer ?? "",
          document.summary,
          ...document.tags,
        ].join(" "),
      );
      const lexicalScore = queryTerms.reduce(
        (score, term) => score + (searchable.includes(term) ? 4 : 0),
        0,
      );
      const relationScore =
        (document.relatedTurbineIds.includes(normalizedTurbineId) ? 7 : 0) +
        (document.relatedMissionIds.includes(missionId) ? 6 : 0);
      const vectorizedScore = document.vectorized ? 1 : 0;
      const curatedBoost =
        (curatedBoostByDocumentId[document.id] ?? 0) +
        (document.id === preferredDocumentId ? 40 : 0);

      return {
        document,
        score: lexicalScore + relationScore + vectorizedScore + curatedBoost,
      };
    })
    .sort(
      (left, right) =>
        right.score - left.score || left.document.id.localeCompare(right.document.id),
    );
}

const evidenceById = new Map(evidenceItems.map((item) => [item.id, item]));

const citationSummaryByDocumentId: Readonly<Record<string, string>> = {
  "KB-SCADA-REPORT-023":
    "WT-023 的主轴承振动 RMS 在 24 小时内由 3.79 升至 4.81 mm/s（+27%），温度高于同工况 30 日基线 8.4°C。",
  "KB-CASE-2019-017":
    "历史案例同时出现振动、温升和包络谱特征；当前案例与其相似度为 0.91，支持早期滚道退化判断。",
  "KB-MB-PROC-004":
    "规程要求把振动复测、温度核验、润滑脂取样和内窥镜检查作为联合取证步骤，不能依据单点越限直接定性。",
  "KB-INSPECTION-023-2026Q2":
    "Q2 巡检记录驱动端润滑脂颜色轻微变深，为本次异常提供了先前状态和润滑劣化线索。",
  "KB-GW165-OM-001": "设备手册给出主轴承振动、温度和停机阈值，可用于校核告警与诊断处置边界。",
};

function createCitation(document: KnowledgeDocument): SourceCitation {
  const page = Math.min(pageByDocumentId[document.id] ?? 1, document.pageCount);
  return {
    docId: document.id,
    title: document.title,
    page,
    summary: citationSummaryByDocumentId[document.id] ?? document.summary,
    documentType: document.type,
    href: `/knowledge?document=${encodeURIComponent(document.id)}&page=${page}`,
  };
}

function relatedMainBearingFailures(): readonly FailureCase[] {
  return failureCases
    .filter((failureCase) => failureCase.subsystem === "main-bearing")
    .sort(
      (left, right) =>
        Date.parse(right.detectedAt) - Date.parse(left.detectedAt) ||
        left.id.localeCompare(right.id),
    );
}

const evidenceSummary = (id: (typeof RELATED_EVIDENCE_IDS)[number]): string =>
  evidenceById.get(id)?.summary ?? "对应证据不可用。";

export function answerKnowledgeQuestion(
  question: string,
  options: {
    readonly turbineId?: string;
    readonly missionId?: string;
    readonly documents?: readonly KnowledgeDocument[];
    readonly workflowSnapshot?: ServerWorkflowSnapshot;
  } = {},
): KnowledgeAssistantAnswer {
  const normalizedQuestion = question.trim();
  const turbineId = (options.turbineId ?? featuredMission.turbineId).toUpperCase();
  const missionId = options.missionId ?? featuredMission.id;
  const documents = options.documents ?? knowledgeDocuments;
  const generatedCaseId = options.workflowSnapshot?.knowledgeCaseId ?? null;
  const rankedDocuments = rankKnowledgeDocuments(
    normalizedQuestion,
    turbineId,
    missionId,
    documents,
    generatedCaseId,
  );
  const citations = rankedDocuments.slice(0, 4).map(({ document }) => createCitation(document));
  const supportingFailures = relatedMainBearingFailures().slice(0, 2);

  return {
    responseId: "RAG-DEMO-WT023-0001",
    question: normalizedQuestion,
    scope: { turbineId, missionId },
    answer: {
      headline: generatedCaseId
        ? "WT-023 主轴承处置已完成闭环验证并沉淀知识案例"
        : "多源趋势与故障特征共同指向主轴承早期退化",
      summary:
        "判断不是由单个阈值触发，而是振动、温升、包络谱、联合异常模型、历史相似案例和既往巡检记录相互印证。",
      findings: [
        {
          label: "振动趋势",
          value: "3.79 → 4.81 mm/s · +27%",
          interpretation: evidenceSummary("EV-023-VIB-001"),
          evidenceIds: ["EV-023-VIB-001"],
        },
        {
          label: "温度偏差",
          value: "+8.4°C vs 30 日基线",
          interpretation: evidenceSummary("EV-023-TEMP-002"),
          evidenceIds: ["EV-023-TEMP-002"],
        },
        {
          label: "故障特征",
          value: "BPFO 频带能量 +19%",
          interpretation: evidenceSummary("EV-023-SPECTRUM-005"),
          evidenceIds: ["EV-023-SPECTRUM-005"],
        },
        {
          label: "交叉验证",
          value: "异常评分 0.86 · 案例相似度 0.91",
          interpretation: `${evidenceSummary("EV-023-ANOMALY-004")} ${evidenceSummary("EV-023-HISTORY-006")}`,
          evidenceIds: ["EV-023-ANOMALY-004", "EV-023-HISTORY-006"],
        },
      ],
      conclusion: generatedCaseId
        ? `${generatedCaseId} 已记录五项现场任务、复测结果与健康回写；机组健康度为 ${options.workflowSnapshot?.health.turbineScore ?? 82}，主轴承健康度为 ${options.workflowSnapshot?.health.mainBearingScore ?? 78}。`
        : `${featuredMission.diagnosis ?? "主轴承早期退化"}。综合置信度 ${featuredMission.confidencePercent ?? 87}%；仍需按规程完成润滑脂取样与内窥镜检查后确认根因。`,
      confidencePercent: featuredMission.confidencePercent ?? 87,
    },
    citations,
    retrieval: {
      mode: "deterministic-keyword-demo",
      queryTerms: extractKnowledgeQueryTerms(normalizedQuestion),
      candidateCount: documents.length + failureCases.length,
      retrievedCount: citations.length,
      evidenceIds: RELATED_EVIDENCE_IDS,
      supportingFailureCaseIds: supportingFailures.map((failureCase) => failureCase.id),
    },
    generatedAt: options.workflowSnapshot?.updatedAt ?? SNAPSHOT_AT,
    disclaimer:
      "这是基于固定演示数据、关键词打分和人工校准权重的确定性检索预览，不是生产级 embedding、向量数据库或真实大模型生成结果。",
  };
}
