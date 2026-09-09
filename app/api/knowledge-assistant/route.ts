import { readKnowledgePassageCorpus } from "@/db/knowledge-passage-store";
import { turbines } from "@/lib/farm-data";
import { answerKnowledgeQuestion } from "@/lib/knowledge-assistant";
import { workflowKnowledgePassage } from "@/lib/knowledge-passages";
import { missions, featuredMission } from "@/lib/operations-data";
import { workflowKnowledgeDocument } from "@/lib/server-workflow-overlays";
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

function normalizedScope(value: unknown, fallback: string): string {
  return (value ?? fallback).toString().trim().toUpperCase();
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

  const turbineId = normalizedScope(input.turbineId, featuredMission.turbineId);
  const missionId = normalizedScope(input.missionId, featuredMission.id);
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
