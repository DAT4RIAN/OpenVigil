import { knowledgeDocuments } from "@/lib/knowledge-data";
import { productionKnowledgeDocumentsResponse } from "@/lib/production-domain-adapter";
import { getProductionBackendConfig } from "@/lib/production-runtime";
import { overlayWorkflowKnowledge } from "@/lib/server-workflow-overlays";
import type { KnowledgeDocument, KnowledgeDocumentType } from "@/lib/types";

import { jsonResponse, parseBoundedInteger } from "../_shared";
import { readWorkflowForApi } from "../_workflow";

const documentTypes: readonly KnowledgeDocumentType[] = [
  "equipment-manual",
  "maintenance-procedure",
  "incident-case",
  "failure-case",
  "technical-standard",
  "manufacturer-bulletin",
  "historical-work-order",
  "inspection-report",
  "scada-analysis-report",
];

const sortableFields = ["updatedAt", "title", "pageCount", "type"] as const;
type SortField = (typeof sortableFields)[number];
type SortOrder = "asc" | "desc";

const snapshotAt = knowledgeDocuments.reduce(
  (latest, document) => (document.updatedAt > latest ? document.updatedAt : latest),
  knowledgeDocuments[0]?.updatedAt ?? "2026-08-13T00:00:00+08:00",
);

const baseMeta = (extra: Readonly<Record<string, unknown>> = {}) => ({
  deterministic: true,
  persisted: false,
  retrievalMode: "fixture-catalog",
  snapshotAt,
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

const parseInteger = (
  value: string | null,
  name: "page" | "pageSize",
  fallback: number,
  maximum: number,
): number | Response => {
  const parsed = parseBoundedInteger(value, fallback, 1, maximum);
  if (parsed === null) {
    return errorResponse(
      "INVALID_PAGINATION",
      `${name} must be an integer between 1 and ${maximum}.`,
      400,
      { argument: name, received: value },
    );
  }
  return parsed;
};

const compareDocuments = (
  left: KnowledgeDocument,
  right: KnowledgeDocument,
  sort: SortField,
  order: SortOrder,
): number => {
  const direction = order === "asc" ? 1 : -1;
  if (sort === "pageCount") return (left.pageCount - right.pageCount) * direction;
  return left[sort].localeCompare(right[sort], "zh-CN") * direction;
};

export async function GET(request: Request): Promise<Response> {
  if (getProductionBackendConfig().mode === "production") {
    return productionKnowledgeDocumentsResponse(request);
  }
  const searchParams = new URL(request.url).searchParams;
  const query = (searchParams.get("q") ?? "").trim();
  const typeValue = (searchParams.get("type") ?? "all").trim();
  const sortValue = (searchParams.get("sort") ?? "updatedAt").trim();
  const orderValue = (searchParams.get("order") ?? "desc").trim();

  if (query.length > 120) {
    return errorResponse("INVALID_QUERY", "q must contain at most 120 characters.", 400, {
      argument: "q",
      maxLength: 120,
    });
  }
  if (typeValue !== "all" && !documentTypes.includes(typeValue as KnowledgeDocumentType)) {
    return errorResponse("INVALID_DOCUMENT_TYPE", `Unknown document type: ${typeValue}.`, 400, {
      argument: "type",
      allowed: ["all", ...documentTypes],
    });
  }
  if (!sortableFields.includes(sortValue as SortField)) {
    return errorResponse("INVALID_SORT", `Unknown sort field: ${sortValue}.`, 400, {
      argument: "sort",
      allowed: sortableFields,
    });
  }
  if (orderValue !== "asc" && orderValue !== "desc") {
    return errorResponse("INVALID_SORT_ORDER", "order must be asc or desc.", 400, {
      argument: "order",
      allowed: ["asc", "desc"],
    });
  }

  const page = parseInteger(searchParams.get("page"), "page", 1, 1_000);
  if (page instanceof Response) return page;
  const pageSize = parseInteger(searchParams.get("pageSize"), "pageSize", 10, 50);
  if (pageSize instanceof Response) return pageSize;

  const workflow = await readWorkflowForApi();
  const catalog = overlayWorkflowKnowledge(knowledgeDocuments, workflow.snapshot);
  const normalizedQuery = query.toLocaleLowerCase("zh-CN");
  const filtered = catalog.filter((document) => {
    if (typeValue !== "all" && document.type !== typeValue) return false;
    if (!normalizedQuery) return true;
    const searchable = [
      document.id,
      document.title,
      document.type,
      document.equipment,
      document.manufacturer ?? "",
      document.version,
      document.summary,
      ...document.tags,
    ]
      .join(" ")
      .toLocaleLowerCase("zh-CN");
    return searchable.includes(normalizedQuery);
  });
  const sorted = [...filtered].sort((left, right) =>
    compareDocuments(left, right, sortValue as SortField, orderValue),
  );
  const offset = (page - 1) * pageSize;
  const documents = sorted.slice(offset, offset + pageSize);
  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const typeCounts = Object.fromEntries(
    documentTypes.map((type) => [
      type,
      catalog.filter((document) => document.type === type).length,
    ]),
  );

  return jsonResponse({
    ok: true,
    data: {
      documents,
      facets: {
        documentTypes: typeCounts,
        vectorized: catalog.filter((document) => document.vectorized).length,
      },
    },
    error: null,
    meta: baseMeta({
      count: documents.length,
      total: sorted.length,
      page,
      pageSize,
      totalPages,
      query: query || null,
      type: typeValue,
      sort: sortValue,
      order: orderValue,
      snapshotAt: workflow.snapshot.updatedAt,
      persisted: workflow.persistence === "d1",
      workflowPersistence: workflow.persistence,
      workflowRevision: workflow.snapshot.revision,
    }),
  });
}
