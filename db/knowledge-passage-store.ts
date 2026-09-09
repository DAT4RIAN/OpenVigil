import { knowledgeDocuments } from "../lib/knowledge-data";
import {
  knowledgePassageFixtureManifest,
  knowledgePassages,
  type KnowledgePassage,
} from "../lib/knowledge-passages";
import type { KnowledgeDocument } from "../lib/types";

export type KnowledgePassagePersistence = "d1" | "fixture";
export type KnowledgePassageRetrievalMode =
  "deterministic-d1-passage-retrieval" | "fixture-passage-fallback";

export interface GroundedKnowledgePassage extends KnowledgePassage {
  readonly documentTitle: string;
  readonly documentType: KnowledgeDocument["type"];
}

export interface KnowledgePassageReadResult {
  readonly passages: readonly GroundedKnowledgePassage[];
  readonly persistence: KnowledgePassagePersistence;
  readonly retrievalMode: KnowledgePassageRetrievalMode;
}

export interface KnowledgePassageReadOptions {
  readonly turbineId: string;
  readonly missionId: string;
  readonly overlayDocument?: KnowledgeDocument | null;
  readonly overlayPassage?: KnowledgePassage | null;
  readonly workflowRevision?: number;
}

interface PassageRow {
  readonly id: string;
  readonly document_id: string;
  readonly page: number;
  readonly section: string;
  readonly body: string;
  readonly content_hash: string;
  readonly token_count: number;
  readonly turbine_id: string | null;
  readonly mission_id: string | null;
  readonly created_at: string;
  readonly updated_at: string;
  readonly document_title: string;
  readonly document_type: KnowledgeDocument["type"];
}

const CREATE_STATEMENTS = [
  `CREATE TABLE IF NOT EXISTS knowledge_documents (
    id TEXT PRIMARY KEY NOT NULL,
    title TEXT NOT NULL,
    type TEXT NOT NULL,
    equipment TEXT NOT NULL,
    version TEXT NOT NULL,
    vectorized INTEGER NOT NULL,
    source_uri TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS knowledge_passages (
    id TEXT PRIMARY KEY NOT NULL,
    document_id TEXT NOT NULL REFERENCES knowledge_documents(id),
    page INTEGER NOT NULL CHECK (page > 0),
    section TEXT NOT NULL,
    body TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    token_count INTEGER NOT NULL CHECK (token_count >= 0),
    turbine_id TEXT,
    mission_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  )`,
  `CREATE INDEX IF NOT EXISTS knowledge_passages_document_page_idx
    ON knowledge_passages (document_id, page)`,
  `CREATE INDEX IF NOT EXISTS knowledge_passages_scope_idx
    ON knowledge_passages (turbine_id, mission_id)`,
  `CREATE UNIQUE INDEX IF NOT EXISTS knowledge_passages_document_hash_uidx
    ON knowledge_passages (document_id, content_hash)`,
] as const;

const initializationByDatabase = new WeakMap<object, Promise<void>>();
const WORKFLOW_DOCUMENT_VERSION = "Server closed-loop v1";

function documentSeedStatement(
  database: D1Database,
  document: KnowledgeDocument,
  upsert: boolean,
): D1PreparedStatement {
  const insertMode = upsert ? "INSERT" : "INSERT OR IGNORE";
  const conflictClause = upsert
    ? ` ON CONFLICT(id) DO UPDATE SET
        title = excluded.title,
        type = excluded.type,
        equipment = excluded.equipment,
        version = excluded.version,
        vectorized = excluded.vectorized,
        source_uri = excluded.source_uri,
        updated_at = excluded.updated_at`
    : "";
  return database
    .prepare(
      `${insertMode} INTO knowledge_documents (
        id, title, type, equipment, version, vectorized, source_uri,
        created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)${conflictClause}`,
    )
    .bind(
      document.id,
      document.title,
      document.type,
      document.equipment,
      document.version,
      document.vectorized ? 1 : 0,
      `/knowledge?document=${encodeURIComponent(document.id)}`,
      document.updatedAt,
      document.updatedAt,
    );
}

function passageSeedStatement(
  database: D1Database,
  passage: KnowledgePassage,
  upsert: boolean,
): D1PreparedStatement {
  const insertMode = upsert ? "INSERT" : "INSERT OR IGNORE";
  const conflictClause = upsert
    ? ` ON CONFLICT(id) DO UPDATE SET
        document_id = excluded.document_id,
        page = excluded.page,
        section = excluded.section,
        body = excluded.body,
        content_hash = excluded.content_hash,
        token_count = excluded.token_count,
        turbine_id = excluded.turbine_id,
        mission_id = excluded.mission_id,
        updated_at = excluded.updated_at`
    : "";
  return database
    .prepare(
      `${insertMode} INTO knowledge_passages (
        id, document_id, page, section, body, content_hash, token_count,
        turbine_id, mission_id, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)${conflictClause}`,
    )
    .bind(
      passage.id,
      passage.documentId,
      passage.page,
      passage.section,
      passage.body,
      passage.contentHash,
      passage.tokenCount,
      passage.turbineId,
      passage.missionId,
      passage.createdAt,
      passage.updatedAt,
    );
}

function retiredFixturePassagesDeleteStatement(database: D1Database): D1PreparedStatement | null {
  const retiredIds = knowledgePassageFixtureManifest.retiredPassageIds;
  if (retiredIds.length === 0) return null;
  return database
    .prepare(`DELETE FROM knowledge_passages WHERE id IN (${retiredIds.map(() => "?").join(", ")})`)
    .bind(...retiredIds);
}

function staleWorkflowPassageCleanupStatement(
  database: D1Database,
  options: KnowledgePassageReadOptions,
): D1PreparedStatement {
  return database
    .prepare(
      `DELETE FROM knowledge_passages
      WHERE turbine_id = ?
        AND mission_id = ?
        AND id = 'KBP-' || document_id || '-006'
        AND EXISTS (
          SELECT 1
          FROM knowledge_documents
          WHERE knowledge_documents.id = knowledge_passages.document_id
            AND knowledge_documents.version = ?
        )
        AND NOT EXISTS (
          SELECT 1
          FROM workflow_instances
          WHERE workflow_instances.turbine_id = knowledge_passages.turbine_id
            AND workflow_instances.mission_id = knowledge_passages.mission_id
            AND workflow_instances.knowledge_case_id = knowledge_passages.document_id
        )`,
    )
    .bind(options.turbineId, options.missionId, WORKFLOW_DOCUMENT_VERSION);
}

function workflowDocumentSyncStatement(
  database: D1Database,
  document: KnowledgeDocument,
  passage: KnowledgePassage,
  workflowRevision: number,
): D1PreparedStatement {
  return database
    .prepare(
      `INSERT INTO knowledge_documents (
        id, title, type, equipment, version, vectorized, source_uri,
        created_at, updated_at
      )
      SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?
      WHERE EXISTS (
        SELECT 1
        FROM workflow_instances
        WHERE mission_id = ?
          AND turbine_id = ?
          AND revision = ?
          AND knowledge_case_id = ?
      )
      ON CONFLICT(id) DO UPDATE SET
        title = excluded.title,
        type = excluded.type,
        equipment = excluded.equipment,
        version = excluded.version,
        vectorized = excluded.vectorized,
        source_uri = excluded.source_uri,
        updated_at = excluded.updated_at`,
    )
    .bind(
      document.id,
      document.title,
      document.type,
      document.equipment,
      document.version,
      document.vectorized ? 1 : 0,
      `/knowledge?document=${encodeURIComponent(document.id)}`,
      document.updatedAt,
      document.updatedAt,
      passage.missionId,
      passage.turbineId,
      workflowRevision,
      document.id,
    );
}

function workflowPassageSyncStatement(
  database: D1Database,
  passage: KnowledgePassage,
  workflowRevision: number,
): D1PreparedStatement {
  return database
    .prepare(
      `INSERT INTO knowledge_passages (
        id, document_id, page, section, body, content_hash, token_count,
        turbine_id, mission_id, created_at, updated_at
      )
      SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
      WHERE EXISTS (
        SELECT 1
        FROM workflow_instances
        WHERE mission_id = ?
          AND turbine_id = ?
          AND revision = ?
          AND knowledge_case_id = ?
      )
      ON CONFLICT(id) DO UPDATE SET
        document_id = excluded.document_id,
        page = excluded.page,
        section = excluded.section,
        body = excluded.body,
        content_hash = excluded.content_hash,
        token_count = excluded.token_count,
        turbine_id = excluded.turbine_id,
        mission_id = excluded.mission_id,
        updated_at = excluded.updated_at`,
    )
    .bind(
      passage.id,
      passage.documentId,
      passage.page,
      passage.section,
      passage.body,
      passage.contentHash,
      passage.tokenCount,
      passage.turbineId,
      passage.missionId,
      passage.createdAt,
      passage.updatedAt,
      passage.missionId,
      passage.turbineId,
      workflowRevision,
      passage.documentId,
    );
}

function workflowPassageSyncStatements(
  database: D1Database,
  options: KnowledgePassageReadOptions,
): D1PreparedStatement[] {
  if (options.workflowRevision === undefined) return [];

  const statements: D1PreparedStatement[] = [
    staleWorkflowPassageCleanupStatement(database, options),
  ];
  const document = options.overlayDocument;
  const passage = options.overlayPassage;
  const validOverlay =
    document &&
    passage &&
    document.id === passage.documentId &&
    document.version === WORKFLOW_DOCUMENT_VERSION &&
    passage.turbineId === options.turbineId &&
    passage.missionId === options.missionId;
  if (!validOverlay) return statements;

  statements.push(
    workflowDocumentSyncStatement(database, document, passage, options.workflowRevision),
    workflowPassageSyncStatement(database, passage, options.workflowRevision),
  );
  return statements;
}

async function initialize(database: D1Database): Promise<void> {
  const identity = database as unknown as object;
  const existing = initializationByDatabase.get(identity);
  if (existing) return existing;

  const initialization = (async () => {
    await database.batch(CREATE_STATEMENTS.map((statement) => database.prepare(statement)));
    const retiredPassagesDelete = retiredFixturePassagesDeleteStatement(database);
    await database.batch([
      ...knowledgeDocuments.map((document) => documentSeedStatement(database, document, true)),
      ...(retiredPassagesDelete ? [retiredPassagesDelete] : []),
      ...knowledgePassages.map((passage) => passageSeedStatement(database, passage, true)),
    ]);
  })();
  initializationByDatabase.set(identity, initialization);
  try {
    await initialization;
  } catch (error) {
    initializationByDatabase.delete(identity);
    throw error;
  }
}

function passageIsInScope(
  passage: KnowledgePassage,
  turbineId: string,
  missionId: string,
): boolean {
  return (
    (passage.turbineId === null || passage.turbineId === turbineId) &&
    (passage.missionId === null || passage.missionId === missionId)
  );
}

function fixturePassages(
  options: KnowledgePassageReadOptions,
): readonly GroundedKnowledgePassage[] {
  const documents = options.overlayDocument
    ? [
        options.overlayDocument,
        ...knowledgeDocuments.filter(({ id }) => id !== options.overlayDocument?.id),
      ]
    : knowledgeDocuments;
  const passages = options.overlayPassage
    ? [
        options.overlayPassage,
        ...knowledgePassages.filter(({ id }) => id !== options.overlayPassage?.id),
      ]
    : knowledgePassages;
  const documentsById = new Map(documents.map((document) => [document.id, document]));
  return passages
    .filter((passage) => passageIsInScope(passage, options.turbineId, options.missionId))
    .map((passage) => {
      const document = documentsById.get(passage.documentId);
      if (!document) return null;
      return {
        ...passage,
        documentTitle: document.title,
        documentType: document.type,
      } satisfies GroundedKnowledgePassage;
    })
    .filter((passage): passage is GroundedKnowledgePassage => passage !== null)
    .sort((left, right) => left.id.localeCompare(right.id));
}

function rowToPassage(row: PassageRow): GroundedKnowledgePassage {
  return {
    id: row.id,
    documentId: row.document_id,
    page: row.page,
    section: row.section,
    body: row.body,
    contentHash: row.content_hash,
    tokenCount: row.token_count,
    turbineId: row.turbine_id,
    missionId: row.mission_id,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    documentTitle: row.document_title,
    documentType: row.document_type,
  };
}

export async function readKnowledgePassageCorpus(
  database: D1Database | undefined,
  options: KnowledgePassageReadOptions,
): Promise<KnowledgePassageReadResult> {
  if (!database) {
    return {
      passages: fixturePassages(options),
      persistence: "fixture",
      retrievalMode: "fixture-passage-fallback",
    };
  }

  await initialize(database);
  const workflowSyncStatements = workflowPassageSyncStatements(database, options);
  if (workflowSyncStatements.length > 0) {
    await database.batch(workflowSyncStatements);
  }

  const result = await database
    .prepare(
      `SELECT
        passage.id,
        passage.document_id,
        passage.page,
        passage.section,
        passage.body,
        passage.content_hash,
        passage.token_count,
        passage.turbine_id,
        passage.mission_id,
        passage.created_at,
        passage.updated_at,
        document.title AS document_title,
        document.type AS document_type
      FROM knowledge_passages AS passage
      INNER JOIN knowledge_documents AS document ON document.id = passage.document_id
      WHERE (passage.turbine_id IS NULL OR passage.turbine_id = ?)
        AND (passage.mission_id IS NULL OR passage.mission_id = ?)
      ORDER BY passage.id ASC`,
    )
    .bind(options.turbineId, options.missionId)
    .all<PassageRow>();

  return {
    passages: result.results.map(rowToPassage),
    persistence: "d1",
    retrievalMode: "deterministic-d1-passage-retrieval",
  };
}
