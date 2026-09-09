import type {
  GroundedKnowledgePassage,
  KnowledgePassageRetrievalMode,
} from "../db/knowledge-passage-store";
import { failureCases } from "./archive-data";
import { evidenceItems, featuredMission } from "./operations-data";
import type { ServerWorkflowSnapshot } from "./server-workflow-contract";
import type { FailureCase, KnowledgeDocument } from "./types";

export const DEFAULT_KNOWLEDGE_QUESTION = "WT-023为什么被判断为主轴承退化？";

export interface SourceCitation {
  readonly passageId: string;
  readonly docId: string;
  readonly title: string;
  readonly page: number;
  readonly section: string;
  /** Verbatim excerpt cut from the retrieved passage body. */
  readonly quote: string;
  /** Backward-compatible display alias, also grounded in the passage body. */
  readonly summary: string;
  readonly score: number;
  readonly documentType: KnowledgeDocument["type"];
  readonly href: string;
}

export interface KnowledgeFinding {
  readonly label: string;
  readonly value: string;
  readonly interpretation: string;
  readonly evidenceIds: readonly string[];
  readonly citationIds: readonly string[];
  readonly passageIds: readonly string[];
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
    readonly mode: KnowledgePassageRetrievalMode;
    readonly queryTerms: readonly string[];
    readonly candidateCount: number;
    readonly retrievedCount: number;
    readonly evidenceIds: readonly string[];
    readonly supportingFailureCaseIds: readonly string[];
  };
  readonly generatedAt: string;
  readonly disclaimer: string;
}

export interface RankedPassage {
  readonly passage: GroundedKnowledgePassage;
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

const domainPhrases = [
  "主轴承退化",
  "历史案例",
  "润滑脂",
  "内窥镜",
  "闭环验证",
  "健康度",
  "齿轮箱",
  "磨粒",
] as const;

const domainTerms = [
  "主轴承",
  "退化",
  "振动",
  "温度",
  "温升",
  "包络谱",
  "基线",
  "趋势",
  "润滑",
  "复测",
  "取样",
  "检查",
  "闭环",
  "验证",
  "审批",
  "任务",
  "健康",
  "故障",
  "案例",
  "齿面",
] as const;

const diagnosticQueryMarkers = [
  "为什么",
  "为何",
  "判断",
  "诊断",
  "退化",
  "故障",
  "异常",
  "根因",
  "原因",
  "bpfo",
  "0.86",
  "0.91",
] as const;

const closedLoopQueryMarkers = ["闭环", "验证", "健康", "回写", "案例"] as const;

const cjkStopTerms = new Set([
  "为什么",
  "是什么",
  "有什么",
  "哪些",
  "什么",
  "为何",
  "如何",
  "怎么",
  "请问",
  "是否",
  "以及",
  "当前",
  "这个",
]);

const normalize = (value: string): string =>
  value.normalize("NFKC").trim().toLocaleLowerCase("zh-CN");

function extractCjkNgrams(normalized: string): readonly string[] {
  const terms: string[] = [];
  const runs = normalized.match(/\p{Script=Han}{2,}/gu) ?? [];
  for (const run of runs) {
    const characters = [...run];
    if (characters.length <= 4 && !cjkStopTerms.has(run)) terms.push(run);
    for (let size = 2; size <= Math.min(4, characters.length); size += 1) {
      for (let offset = 0; offset <= characters.length - size; offset += 1) {
        const term = characters.slice(offset, offset + size).join("");
        if (!cjkStopTerms.has(term)) terms.push(term);
      }
    }
  }
  return [...new Set(terms)].slice(0, 96);
}

export function extractKnowledgeQueryTerms(question: string): readonly string[] {
  const normalized = normalize(question);
  const latinTerms = normalized.match(/[a-z]+(?:-[a-z0-9]+)*|\d+(?:\.\d+)?(?:%|°c)?/g) ?? [];
  const phrases = domainPhrases.filter((term) => normalized.includes(term));
  const matchedTerms = domainTerms.filter((term) => normalized.includes(term));
  const cjkTerms = extractCjkNgrams(normalized);
  return [...new Set([...phrases, ...matchedTerms, ...latinTerms, ...cjkTerms])].sort();
}

function countOccurrences(text: string, term: string): number {
  if (!term) return 0;
  let count = 0;
  let offset = 0;
  while (offset < text.length) {
    const found = text.indexOf(term, offset);
    if (found < 0) break;
    count += 1;
    offset = found + term.length;
  }
  return count;
}

function isPhrase(term: string): boolean {
  return domainPhrases.includes(term as (typeof domainPhrases)[number]) || term.includes("-");
}

/** Passage-body-only scoring; metadata affects neither rank nor citation text. */
export function rankKnowledgePassages(
  question: string,
  passages: readonly GroundedKnowledgePassage[],
): readonly RankedPassage[] {
  const queryTerms = extractKnowledgeQueryTerms(question);
  if (queryTerms.length === 0) return [];

  return passages
    .map((passage) => {
      const body = normalize(passage.body);
      const score = queryTerms.reduce((total, term) => {
        const occurrences = countOccurrences(body, term);
        if (occurrences === 0) return total;
        return total + occurrences * (isPhrase(term) ? 12 : 5);
      }, 0);
      return { passage, score };
    })
    .filter(({ score }) => score > 0)
    .sort(
      (left, right) => right.score - left.score || left.passage.id.localeCompare(right.passage.id),
    );
}

function passageQuote(body: string, queryTerms: readonly string[], maximumLength = 220): string {
  const compact = body.replace(/\s+/g, " ").trim();
  if (compact.length <= maximumLength) return compact;
  const normalized = normalize(compact);
  const firstMatch = queryTerms
    .map((term) => normalized.indexOf(term))
    .filter((index) => index >= 0)
    .sort((left, right) => left - right)[0];
  const start = Math.max(0, (firstMatch ?? 0) - 36);
  const end = Math.min(compact.length, start + maximumLength);
  return `${start > 0 ? "…" : ""}${compact.slice(start, end)}${end < compact.length ? "…" : ""}`;
}

function createCitation(ranked: RankedPassage, queryTerms: readonly string[]): SourceCitation {
  const quote = passageQuote(ranked.passage.body, queryTerms);
  return {
    passageId: ranked.passage.id,
    docId: ranked.passage.documentId,
    title: ranked.passage.documentTitle,
    page: ranked.passage.page,
    section: ranked.passage.section,
    quote,
    summary: quote,
    score: ranked.score,
    documentType: ranked.passage.documentType,
    href: `/knowledge?document=${encodeURIComponent(ranked.passage.documentId)}&page=${ranked.passage.page}&passage=${encodeURIComponent(ranked.passage.id)}`,
  };
}

const evidenceById = new Map(evidenceItems.map((item) => [item.id, item]));
const evidenceSummary = (id: (typeof RELATED_EVIDENCE_IDS)[number]): string =>
  evidenceById.get(id)?.summary ?? "对应证据不可用。";

function relatedMainBearingFailures(turbineId: string): readonly FailureCase[] {
  return failureCases
    .filter((failureCase) => failureCase.subsystem === "main-bearing")
    .sort(
      (left, right) =>
        Number(right.turbineId === turbineId) - Number(left.turbineId === turbineId) ||
        Date.parse(right.detectedAt) - Date.parse(left.detectedAt) ||
        left.id.localeCompare(right.id),
    );
}

function citationReferences(
  citations: readonly SourceCitation[],
  bodyTerms: readonly string[],
): Pick<KnowledgeFinding, "citationIds" | "passageIds"> {
  const matching = citations.filter((citation) => {
    const quote = normalize(citation.quote);
    return bodyTerms.some((term) => quote.includes(normalize(term)));
  });
  return {
    citationIds: matching.map((citation) => citation.passageId),
    passageIds: matching.map((citation) => citation.passageId),
  };
}

function genericFindings(citations: readonly SourceCitation[]): readonly KnowledgeFinding[] {
  return citations.slice(0, 3).map((citation) => ({
    label: citation.section,
    value: `${citation.title} · 第 ${citation.page} 页`,
    interpretation: citation.quote,
    evidenceIds: [],
    citationIds: [citation.passageId],
    passageIds: [citation.passageId],
  }));
}

function isFeaturedScope(turbineId: string, missionId: string): boolean {
  return turbineId === featuredMission.turbineId && missionId === featuredMission.id;
}

export function answerKnowledgeQuestion(
  question: string,
  options: {
    readonly turbineId: string;
    readonly missionId: string;
    readonly passages: readonly GroundedKnowledgePassage[];
    readonly retrievalMode: KnowledgePassageRetrievalMode;
    readonly workflowSnapshot?: ServerWorkflowSnapshot;
  },
): KnowledgeAssistantAnswer {
  const normalizedQuestion = question.trim();
  const turbineId = options.turbineId.toUpperCase();
  const missionId = options.missionId.toUpperCase();
  const queryTerms = extractKnowledgeQueryTerms(normalizedQuestion);
  const rankedPassages = rankKnowledgePassages(normalizedQuestion, options.passages);
  const citations = rankedPassages.slice(0, 7).map((ranked) => createCitation(ranked, queryTerms));
  const featured = isFeaturedScope(turbineId, missionId);
  const normalizedForIntent = normalize(normalizedQuestion);
  const diagnosticQuestion = diagnosticQueryMarkers.some((term) =>
    normalizedForIntent.includes(term),
  );
  const closedLoopQuestion = closedLoopQueryMarkers.some((term) =>
    normalizedForIntent.includes(term),
  );

  const featuredFindings: readonly KnowledgeFinding[] = [
    {
      label: "振动趋势",
      value: "3.79 → 4.81 mm/s · +27%",
      interpretation: evidenceSummary("EV-023-VIB-001"),
      evidenceIds: ["EV-023-VIB-001"],
      ...citationReferences(citations, ["3.79", "4.81", "27%"]),
    },
    {
      label: "温度偏差",
      value: "+8.4°C vs 30 日基线",
      interpretation: evidenceSummary("EV-023-TEMP-002"),
      evidenceIds: ["EV-023-TEMP-002"],
      ...citationReferences(citations, ["8.4°c", "30 日基线"]),
    },
    {
      label: "故障特征",
      value: "BPFO 频带能量 +19%",
      interpretation: evidenceSummary("EV-023-SPECTRUM-005"),
      evidenceIds: ["EV-023-SPECTRUM-005"],
      ...citationReferences(citations, ["bpfo", "19%"]),
    },
    {
      label: "交叉验证",
      value: "异常评分 0.86 · 案例相似度 0.91",
      interpretation: `${evidenceSummary("EV-023-ANOMALY-004")} ${evidenceSummary("EV-023-HISTORY-006")}`,
      evidenceIds: ["EV-023-ANOMALY-004", "EV-023-HISTORY-006"],
      ...citationReferences(citations, ["0.86", "0.91", "案例"]),
    },
  ];

  const noEvidence = citations.length === 0;
  const groundedFeaturedFindings = featuredFindings.filter(
    (finding) => finding.citationIds.length > 0,
  );
  const useFeaturedDiagnosis =
    featured && diagnosticQuestion && groundedFeaturedFindings.length >= 2;
  const workflowCaseId = featured ? (options.workflowSnapshot?.knowledgeCaseId ?? null) : null;
  const generatedCaseId =
    workflowCaseId &&
    closedLoopQuestion &&
    citations.some((citation) => citation.docId === workflowCaseId)
      ? workflowCaseId
      : null;
  const supportingFailures = useFeaturedDiagnosis
    ? relatedMainBearingFailures(turbineId).slice(0, 2)
    : [];
  const findings = noEvidence
    ? []
    : useFeaturedDiagnosis
      ? groundedFeaturedFindings
      : genericFindings(citations);
  const confidencePercent = noEvidence
    ? 0
    : useFeaturedDiagnosis
      ? (featuredMission.confidencePercent ?? 87)
      : Math.min(72, 38 + citations.length * 7);

  return {
    responseId: `KAR-${turbineId}-${missionId}-${queryTerms.join("-") || "NO-EVIDENCE"}`,
    question: normalizedQuestion,
    scope: { turbineId, missionId },
    answer: {
      headline: noEvidence
        ? "当前范围内没有可引用的知识段落"
        : generatedCaseId
          ? "WT-023 主轴承处置已完成闭环验证并沉淀知识案例"
          : useFeaturedDiagnosis
            ? "多源趋势与故障特征共同指向主轴承早期退化"
            : "已从当前机组与任务范围检索到相关知识段落",
      summary: noEvidence
        ? "系统不会在缺少 passage 级证据时生成设备诊断结论。请补充更具体的部件、现象或指标关键词。"
        : useFeaturedDiagnosis
          ? "振动、温升、包络谱、异常评分、历史案例和巡检记录在 passage 级证据中相互印证。"
          : `找到 ${citations.length} 条与问题直接匹配的 passage 级证据，以下内容仅概括这些来源。`,
      findings,
      conclusion: noEvidence
        ? "证据不足，未形成诊断结论。"
        : generatedCaseId
          ? `${generatedCaseId} 已记录五项现场任务、复测结果与健康回写；机组健康度为 ${options.workflowSnapshot?.health.turbineScore ?? 82}，主轴承健康度为 ${options.workflowSnapshot?.health.mainBearingScore ?? 78}。`
          : useFeaturedDiagnosis
            ? `${featuredMission.diagnosis ?? "主轴承早期退化"}。综合置信度 ${featuredMission.confidencePercent ?? 87}%；仍需按规程完成润滑脂取样与内窥镜检查后确认根因。`
            : "结论仅限已检索段落；当前实现不外推未被来源正文支持的故障判断。",
      confidencePercent,
    },
    citations,
    retrieval: {
      mode: options.retrievalMode,
      queryTerms,
      candidateCount: options.passages.length,
      retrievedCount: citations.length,
      evidenceIds: useFeaturedDiagnosis ? RELATED_EVIDENCE_IDS : [],
      supportingFailureCaseIds: supportingFailures.map((failureCase) => failureCase.id),
    },
    generatedAt: options.workflowSnapshot?.updatedAt ?? SNAPSHOT_AT,
    disclaimer:
      "这是 passage 正文上的确定性词项与短语检索，不使用 embedding、向量数据库或大模型隐式推理；引用内容均可回溯到来源段落。",
  };
}
