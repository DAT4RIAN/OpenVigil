import { text, list, record, backendCollection } from "./shared.ts";

const knowledgeDocumentTypes = new Set([
  "equipment-manual",
  "maintenance-procedure",
  "incident-case",
  "failure-case",
  "technical-standard",
  "manufacturer-bulletin",
  "historical-work-order",
  "inspection-report",
  "scada-analysis-report",
]);

export async function productionKnowledgeDocumentsResponse(request: Request): Promise<Response> {
  const sourceUrl = new URL(request.url);
  const backendUrl = new URL(request.url);
  backendUrl.search = "";
  const query = sourceUrl.searchParams.get("q");
  const type = sourceUrl.searchParams.get("type");
  if (query) backendUrl.searchParams.set("q", query);
  if (type && type !== "all") backendUrl.searchParams.set("document_type", type);
  backendUrl.searchParams.set("limit", "200");
  const result = await backendCollection(
    new Request(backendUrl, request),
    "/api/v1/knowledge/documents",
    "documents",
  );
  if (result instanceof Response) return result;
  const documents = result.rows.map((row) => {
    const metadata = record(row.metadata);
    const sourceLayout = record(row.source_layout);
    const documentType = text(row.document_type, "technical-standard");
    return {
      id: text(row.document_id),
      title: text(row.title),
      type: knowledgeDocumentTypes.has(documentType) ? documentType : "technical-standard",
      equipment: text(metadata.equipment, "未标注"),
      manufacturer: text(metadata.manufacturer) || null,
      version: text(row.document_version, "1"),
      updatedAt: text(row.updated_at, text(row.created_at)),
      vectorized: row.vectorized === true,
      pageCount:
        typeof sourceLayout.page_count === "number" && sourceLayout.page_count > 0
          ? sourceLayout.page_count
          : null,
      language: text(metadata.language, "zh-CN") === "en-US" ? "en-US" : "zh-CN",
      tags: list(metadata.tags).map(String),
      summary: text(metadata.summary, text(row.title)),
      relatedTurbineIds: list(metadata.related_turbine_ids).map(String),
      relatedMissionIds: list(metadata.related_mission_ids).map(String),
      ingestionStatus: text(row.ingestion_status, "pending"),
      embeddingProvider: text(row.embedding_provider) || null,
      embeddingModel: text(row.embedding_model) || null,
      artifactUri: text(row.artifact_uri) || null,
      artifactSha256: text(row.artifact_sha256) || null,
    };
  });
  return Response.json(
    {
      ok: true,
      data: {
        documents,
        facets: {
          vectorized: documents.filter((document) => document.vectorized).length,
        },
      },
      error: null,
      meta: {
        count: documents.length,
        total: result.total,
        nextCursor: result.nextCursor,
        hasMore: !result.complete,
        deterministic: false,
        persisted: true,
        runtimeMode: "production",
        source: "python-fastapi",
        fixtureFallback: false,
      },
    },
    { headers: { "cache-control": "no-store" } },
  );
}
