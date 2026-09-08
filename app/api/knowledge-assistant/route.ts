import { answerKnowledgeQuestion } from "@/lib/knowledge-assistant";
import { knowledgeDocuments } from "@/lib/knowledge-data";
import { featuredMission } from "@/lib/operations-data";
import { overlayWorkflowKnowledge } from "@/lib/server-workflow-overlays";

import { jsonResponse } from "../_shared";
import { readWorkflowForApi } from "../_workflow";

const SNAPSHOT_AT = "2026-08-13T10:24:00+08:00";
const allowedFields = new Set(["question", "turbineId", "missionId"]);

const baseMeta = (extra: Readonly<Record<string, unknown>> = {}) => ({
  deterministic: true,
  persisted: false,
  retrievalMode: "deterministic-keyword-demo",
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

  const turbineId = (input.turbineId ?? featuredMission.turbineId).toString().trim().toUpperCase();
  const missionId = (input.missionId ?? featuredMission.id).toString().trim().toUpperCase();
  if (turbineId !== featuredMission.turbineId || missionId !== featuredMission.id) {
    return errorResponse(
      "UNSUPPORTED_DEMO_SCOPE",
      "The deterministic knowledge preview currently supports WT-023 / MISSION-2026-0823 only.",
      422,
      {
        turbineId,
        missionId,
        supported: {
          turbineId: featuredMission.turbineId,
          missionId: featuredMission.id,
        },
      },
    );
  }

  const workflow = await readWorkflowForApi();
  const documents = overlayWorkflowKnowledge(knowledgeDocuments, workflow.snapshot);
  const answer = answerKnowledgeQuestion(question, {
    turbineId,
    missionId,
    documents,
    workflowSnapshot: workflow.snapshot,
  });
  return jsonResponse({
    ok: true,
    data: { answer },
    error: null,
    meta: baseMeta({
      citationCount: answer.citations.length,
      candidateCount: answer.retrieval.candidateCount,
      persisted: workflow.persistence === "d1",
      snapshotAt: workflow.snapshot.updatedAt,
      workflowPersistence: workflow.persistence,
      workflowRevision: workflow.snapshot.revision,
      knowledgeCaseId: workflow.snapshot.knowledgeCaseId,
    }),
  });
}
