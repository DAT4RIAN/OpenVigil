import { readKnowledgePassageCorpus } from "@/db/knowledge-passage-store";
import { turbines } from "@/lib/farm-data";
import { answerKnowledgeQuestion } from "@/lib/knowledge-assistant";
import { workflowKnowledgePassage } from "@/lib/knowledge-passages";
import { missions, featuredMission } from "@/lib/operations-data";
import { workflowKnowledgeDocument } from "@/lib/server-workflow-overlays";
import {
  getProductionBackendConfig,
  proxyProductionBackendRequest,
} from "@/lib/production-runtime";
import { getWorkerEnv } from "@/lib/worker-env";

import { jsonResponse } from "../_shared";
import { readWorkflowForApi } from "../_workflow";

const SNAPSHOT_AT = "2026-08-13T10:24:00+08:00";
const allowedFields = new Set(["question", "turbineId", "missionId"]);

const baseMeta = (extra: Readonly<Record<string, unknown>> = {}) => ({
  deterministic: true,
  persisted: false,
  persistence: "fixture",
  retrievalMode: "fixture-passage-fallback",
  realEmbedding: false,
  snapshotAt: SNAPSHOT_AT,
  ...extra,
});

const errorResponse = (
  code: string,
  message: string,
  status: number,
  details: Readonly<Record<string, unknown>> | null = null,
): Response =>
  jsonResponse(
    {
      ok: false,
      data: null,
      error: { code, message, details },
      meta: baseMeta(),
    },
    status,
  );

function normalizedScope(value: unknown, fallback: string | null): string | null {
  const text =
    typeof value === "string" ? value : typeof value === "number" ? String(value) : fallback;
  if (typeof text !== "string") return fallback;
  const normalized = text.trim().toUpperCase();
  return normalized || fallback;
}

export async function POST(request: Request): Promise<Response> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return errorResponse("INVALID_JSON", "Request body must be valid JSON.", 400);
  }

  if (typeof body !== "object" || body === null || Array.isArray(body)) {
    return errorResponse(
      "INVALID_REQUEST",
      "Request body must be an object with a question field.",
      400,
    );
  }

  const input = body as Record<string, unknown>;
  const unknownFields = Object.keys(input).filter((field) => !allowedFields.has(field));
  if (unknownFields.length > 0) {
    return errorResponse("UNKNOWN_FIELDS", "Request contains unsupported fields.", 400, {
      fields: unknownFields.sort(),
      allowed: [...allowedFields],
    });
  }
  if (typeof input.question !== "string" || input.question.trim().length === 0) {
    return errorResponse("INVALID_QUESTION", "question must be a non-empty string.", 400, {
      argument: "question",
    });
  }
  const question = input.question.trim();
  if (question.length > 500) {
    return errorResponse("INVALID_QUESTION", "question must contain at most 500 characters.", 400, {
      argument: "question",
      maxLength: 500,
    });
  }
  if (input.turbineId !== undefined && typeof input.turbineId !== "string") {
    return errorResponse("INVALID_SCOPE", "turbineId must be a string when provided.", 400, {
      argument: "turbineId",
    });
  }
  if (input.missionId !== undefined && typeof input.missionId !== "string") {
    return errorResponse("INVALID_SCOPE", "missionId must be a string when provided.", 400, {
      argument: "missionId",
    });
  }

  const productionMode = getProductionBackendConfig().mode === "production";
  const turbineId = normalizedScope(
    input.turbineId,
    productionMode ? null : featuredMission.turbineId,
  );
  const missionId = normalizedScope(input.missionId, productionMode ? null : featuredMission.id);
  if (productionMode) {
    const gatewayUrl = new URL(request.url);
    gatewayUrl.search = "";
    gatewayUrl.searchParams.set("query", question);
    if (turbineId) gatewayUrl.searchParams.set("entityId", turbineId);
    const upstream = await proxyProductionBackendRequest(
      new Request(gatewayUrl, { method: "GET", headers: request.headers }),
      "/api/v1/knowledge-graph/search",
    );
    if (!upstream.ok) return upstream;
    const payload = (await upstream.json()) as {
      data?: {
        matches?: Array<{
          match_type?: string;
          document_id?: string;
          passageId?: string;
          excerpt?: string;
          title?: string;
          fusedScore?: number;
          similarity?: number;
          citation_href?: string;
          case_id?: string;
        }>;
        answer?: string;
        answerMode?: string;
      };
    };
    const matches = Array.isArray(payload.data?.matches) ? payload.data.matches : [];
    const citations = matches
      .filter((match) => match.match_type === "knowledge_document")
      .map((match) => {
        const documentId = String(match.document_id ?? "");
        const passageId = String(match.passageId ?? `${documentId}#body`);
        const quote = String(match.excerpt ?? "");
        return {
          passageId,
          docId: documentId,
          title: String(match.title ?? documentId),
          page: 1,
          section: "向量检索正文",
          quote,
          summary: quote,
          score: Number(match.fusedScore ?? match.similarity ?? 0),
          documentType: "technical-standard" as const,
          href: String(
            match.citation_href ?? `/knowledge?document=${encodeURIComponent(documentId)}`,
          ),
        };
      });
    const topScore = citations[0]?.score ?? 0;
    const answer = {
      responseId: `KAR-PROD-${Date.now()}`,
      question,
      scope: { turbineId, missionId },
      answer: {
        headline:
          citations.length > 0
            ? `已找到 ${citations.length} 条可追溯知识证据`
            : "没有找到可引用证据",
        summary: payload.data?.answer ?? "当前生产知识库没有返回可解释证据。",
        findings: citations.map((citation) => ({
          label: citation.title,
          value: `融合得分 ${citation.score.toFixed(3)}`,
          interpretation: citation.quote,
          evidenceIds: [],
          citationIds: [citation.passageId],
          passageIds: [citation.passageId],
        })),
        conclusion:
          payload.data?.answerMode === "grounded-retrieval-summary-no-generative-claim"
            ? "该结果只总结已检索证据，不生成超出来源的诊断结论。"
            : "请由有资质人员复核检索证据后再用于运维决策。",
        confidencePercent: Math.round(Math.max(0, Math.min(1, topScore)) * 100),
      },
      citations,
      retrieval: {
        mode: "production-pgvector-neo4j-hybrid" as const,
        queryTerms: question.split(/\s+/).filter(Boolean),
        candidateCount: matches.length,
        retrievedCount: citations.length,
        evidenceIds: [],
        supportingFailureCaseIds: matches
          .filter((match) => match.match_type === "resolved_case")
          .map((match) => String(match.case_id ?? ""))
          .filter(Boolean),
      },
      generatedAt: new Date().toISOString(),
      disclaimer: "生产检索结果必须结合原始文档、设备状态和审批流程人工复核。",
    };
    return jsonResponse({
      ok: true,
      data: { answer },
      error: null,
      meta: {
        deterministic: false,
        persisted: true,
        persistence: "postgresql-pgvector-neo4j",
        retrievalMode: "production-pgvector-neo4j-hybrid",
        realEmbedding: true,
        fixtureFallback: false,
        citationCount: citations.length,
      },
    });
  }
  if (turbineId === null || missionId === null) {
    return errorResponse(
      "INVALID_SCOPE",
      "Demo knowledge questions require a turbineId and missionId.",
      422,
    );
  }
  const turbine = turbines.find((candidate) => candidate.id === turbineId);
  if (!turbine) {
    return errorResponse("TURBINE_NOT_FOUND", `Wind turbine ${turbineId} was not found.`, 422, {
      turbineId,
    });
  }
  const mission = missions.find((candidate) => candidate.id === missionId);
  if (!mission) {
    return errorResponse("MISSION_NOT_FOUND", `Mission ${missionId} was not found.`, 422, {
      missionId,
    });
  }
  if (mission.turbineId !== turbineId) {
    return errorResponse(
      "MISSION_TURBINE_MISMATCH",
      `Mission ${missionId} belongs to ${mission.turbineId}, not ${turbineId}.`,
      422,
      { missionId, turbineId, missionTurbineId: mission.turbineId },
    );
  }

  const workflow = await readWorkflowForApi();
  const workflowApplies =
    workflow.snapshot.turbineId === turbineId && workflow.snapshot.mission.id === missionId;
  const overlayDocument = workflowApplies ? workflowKnowledgeDocument(workflow.snapshot) : null;
  const overlayPassage = workflowApplies ? workflowKnowledgePassage(workflow.snapshot) : null;
  const corpus = await readKnowledgePassageCorpus(getWorkerEnv().DB, {
    turbineId,
    missionId,
    overlayDocument,
    overlayPassage,
    ...(workflowApplies ? { workflowRevision: workflow.snapshot.revision } : {}),
  });
  const answer = answerKnowledgeQuestion(question, {
    turbineId,
    missionId,
    passages: corpus.passages,
    retrievalMode: corpus.retrievalMode,
    ...(workflowApplies ? { workflowSnapshot: workflow.snapshot } : {}),
  });

  return jsonResponse({
    ok: true,
    data: { answer },
    error: null,
    meta: baseMeta({
      citationCount: answer.citations.length,
      candidateCount: answer.retrieval.candidateCount,
      persisted: corpus.persistence === "d1",
      persistence: corpus.persistence,
      retrievalMode: corpus.retrievalMode,
      snapshotAt: workflowApplies ? workflow.snapshot.updatedAt : SNAPSHOT_AT,
      workflowPersistence: workflow.persistence,
      workflowRevision: workflowApplies ? workflow.snapshot.revision : null,
      knowledgeCaseId: workflowApplies ? workflow.snapshot.knowledgeCaseId : null,
    }),
  });
}
