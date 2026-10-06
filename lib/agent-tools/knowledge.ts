import type { AgentToolArguments, AgentToolExecutionContext } from "./contracts";
import { requiredTurbine, round, workflowSnapshotAt } from "./helpers";
import type { KnowledgeDocumentType, SubsystemKey } from "../types";
import { subsystemHealth } from "../telemetry-data";
import { failureCases } from "../archive-data";
import { windFarm } from "../farm-data";
import { overlayWorkflowKnowledge } from "../server-workflow-overlays";
import { knowledgeDocuments } from "../knowledge-data";
import { AgentToolRuntimeError } from "./contracts";

export const querySimilarFailures = (args: AgentToolArguments): unknown => {
  const turbineId = args.turbineId as string;
  requiredTurbine(turbineId);
  const requestedSubsystem = args.subsystem as SubsystemKey | undefined;
  const inferredSubsystem = [...subsystemHealth]
    .filter((item) => item.turbineId === turbineId)
    .sort(
      (left, right) => left.healthScore - right.healthScore || left.id.localeCompare(right.id),
    )[0]?.key;
  const subsystem = requestedSubsystem ?? inferredSubsystem ?? "main-bearing";
  const limit = args.limit as number;
  const ranked = failureCases
    .map((failure) => {
      const subsystemMatch = failure.subsystem === subsystem;
      const sameTurbine = failure.turbineId === turbineId;
      const highRiskMatch = failure.severity === "high" || failure.severity === "critical";
      const similarityScore = round(
        Math.min(
          0.99,
          0.51 +
            (subsystemMatch ? 0.34 : 0) +
            (sameTurbine ? 0.06 : 0) +
            (highRiskMatch ? 0.04 : 0),
        ),
        2,
      );
      return { failure, similarityScore, subsystemMatch, sameTurbine };
    })
    .sort(
      (left, right) =>
        right.similarityScore - left.similarityScore ||
        Date.parse(right.failure.detectedAt) - Date.parse(left.failure.detectedAt) ||
        left.failure.id.localeCompare(right.failure.id),
    )
    .slice(0, limit);

  return {
    snapshotAt: windFarm.lastUpdatedAt,
    turbineId,
    targetSubsystem: subsystem,
    rankingMethod: "fixture subsystem + turbine + severity weighted match",
    cases: ranked.map(({ failure, similarityScore, subsystemMatch, sameTurbine }) => ({
      ...failure,
      similarityScore,
      matchReasons: [
        ...(subsystemMatch ? ["same-subsystem"] : []),
        ...(sameTurbine ? ["same-turbine"] : []),
        ...(failure.severity === "high" || failure.severity === "critical"
          ? ["high-risk-case"]
          : []),
      ],
    })),
  };
};

export const queryManual = (
  args: AgentToolArguments,
  context: AgentToolExecutionContext,
): unknown => {
  const query = (args.query as string | undefined)?.toLowerCase() ?? null;
  const documentId = (args.documentId as string | undefined) ?? null;
  const turbineId = (args.turbineId as string | undefined) ?? null;
  const type = (args.type as KnowledgeDocumentType | undefined) ?? null;
  const limit = args.limit as number;
  if (turbineId) requiredTurbine(turbineId);

  const documents = context.workflowSnapshot
    ? overlayWorkflowKnowledge(knowledgeDocuments, context.workflowSnapshot)
    : knowledgeDocuments;
  if (documentId && !documents.some((document) => document.id === documentId)) {
    throw new AgentToolRuntimeError(
      "KNOWLEDGE_DOCUMENT_NOT_FOUND",
      `Knowledge document ${documentId} was not found.`,
      404,
      { documentId },
    );
  }

  const queryTokens = query?.split(/\s+/u).filter(Boolean) ?? [];
  const ranked = documents
    .filter(
      (document) =>
        (!documentId || document.id === documentId) &&
        (!turbineId || document.relatedTurbineIds.includes(turbineId)) &&
        (!type || document.type === type),
    )
    .map((document) => {
      const fields = {
        id: document.id.toLowerCase(),
        title: document.title.toLowerCase(),
        equipment: document.equipment.toLowerCase(),
        tags: document.tags.join(" ").toLowerCase(),
        summary: document.summary.toLowerCase(),
      };
      const searchable = Object.values(fields).join(" ");
      const matchedFields = Object.entries(fields)
        .filter(([, value]) => queryTokens.some((token) => value.includes(token)))
        .map(([field]) => field);
      const tokenHits = queryTokens.filter((token) => searchable.includes(token)).length;
      const exactPhraseMatch = query !== null && searchable.includes(query);
      const relevanceScore =
        (documentId === document.id ? 100 : 0) +
        (turbineId && document.relatedTurbineIds.includes(turbineId) ? 24 : 0) +
        (type === document.type ? 12 : 0) +
        (exactPhraseMatch ? 30 : 0) +
        tokenHits * 6;
      return {
        document,
        matchedFields,
        relevanceScore,
        queryMatched: exactPhraseMatch || tokenHits > 0,
      };
    })
    .filter(({ queryMatched }) => !query || queryMatched)
    .sort(
      (left, right) =>
        right.relevanceScore - left.relevanceScore ||
        Date.parse(right.document.updatedAt) - Date.parse(left.document.updatedAt) ||
        left.document.id.localeCompare(right.document.id),
    );

  return {
    snapshotAt: workflowSnapshotAt(context),
    query,
    filters: { documentId, turbineId, type },
    rankingMethod: "deterministic metadata field matching",
    total: ranked.length,
    returned: Math.min(limit, ranked.length),
    documents: ranked.slice(0, limit).map(({ document, matchedFields, relevanceScore }) => ({
      ...document,
      relevanceScore,
      matchedFields,
      citation: {
        documentId: document.id,
        title: document.title,
        version: document.version,
        sourceType: document.type,
        pageCount: document.pageCount,
      },
    })),
  };
};
