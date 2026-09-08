import { agents } from "../lib/agent-data";
import {
  executeAgentTool,
  getAgentToolExecutionHistory,
  stableAgentToolStringify,
  type AgentToolExecution,
  type AgentToolRequest,
} from "../lib/agent-tool-runtime";
import { turbines, windFarm } from "../lib/farm-data";
import { missions } from "../lib/operations-data";
import type { ServerWorkflowSnapshot } from "../lib/server-workflow-contract";

export type AgentExecutionPersistence = "d1" | "runtime-memory";

export interface AgentExecutionFilters {
  readonly agentId?: string;
  readonly missionId?: string;
  readonly status?: AgentToolExecution["status"];
  readonly toolName?: AgentToolRequest["tool"];
  readonly limit: number;
}

export interface AgentExecutionWriteRequest {
  readonly request: AgentToolRequest;
  readonly agentId: string;
  readonly missionId: string | null;
  readonly idempotencyKey?: string;
  readonly persist: boolean;
  readonly workflowSnapshot?: ServerWorkflowSnapshot;
}

export interface AgentExecutionWriteResult {
  readonly execution: AgentToolExecution;
  readonly persistence: AgentExecutionPersistence;
  readonly replayed: boolean;
}

export interface AgentExecutionReadResult {
  readonly executions: readonly AgentToolExecution[];
  readonly total: number;
  readonly persistence: AgentExecutionPersistence;
}

export class AgentExecutionStoreError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: Readonly<Record<string, unknown>> | null;

  constructor(
    code: string,
    message: string,
    status: number,
    details: Readonly<Record<string, unknown>> | null = null,
  ) {
    super(message);
    this.name = "AgentExecutionStoreError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

interface AgentExecutionRow {
  readonly id: string;
  readonly mission_id: string | null;
  readonly agent_id: string;
  readonly tool_name: string;
  readonly status: string;
  readonly input: unknown;
  readonly output: unknown;
  readonly started_at: string;
  readonly completed_at: string | null;
  readonly latency_ms: number | null;
  readonly token_usage: number | null;
  readonly error: string | null;
  readonly correlation_id: string;
}

interface AgentExecutionInputPayload {
  readonly schemaVersion: "windops.agent-tool-input.v1";
  readonly idempotencyKey: string;
  readonly requestFingerprint: string;
  readonly request: AgentToolRequest;
}

interface AgentExecutionOutputPayload {
  readonly schemaVersion: "windops.agent-tool-output.v1";
  readonly result: AgentToolExecution["result"];
  readonly tokenEstimate: AgentToolExecution["tokenEstimate"];
  readonly deterministic: true;
}

const CREATE_STATEMENTS = [
  `CREATE TABLE IF NOT EXISTS wind_farms (
    id TEXT PRIMARY KEY NOT NULL,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    location TEXT NOT NULL,
    total_capacity_mw REAL NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS wind_turbines (
    id TEXT PRIMARY KEY NOT NULL,
    farm_id TEXT NOT NULL REFERENCES wind_farms(id),
    model TEXT NOT NULL,
    serial_number TEXT NOT NULL UNIQUE,
    rated_power_mw REAL NOT NULL,
    status TEXT NOT NULL,
    health_score REAL NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    layer TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS missions (
    id TEXT PRIMARY KEY NOT NULL,
    turbine_id TEXT NOT NULL REFERENCES wind_turbines(id),
    title TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL,
    progress_percent INTEGER NOT NULL,
    lead_agent_id TEXT NOT NULL REFERENCES agents(id),
    diagnosis TEXT,
    confidence_percent REAL,
    correlation_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  )`,
  `CREATE TABLE IF NOT EXISTS agent_executions (
    id TEXT PRIMARY KEY NOT NULL,
    mission_id TEXT REFERENCES missions(id),
    agent_id TEXT NOT NULL REFERENCES agents(id),
    tool_name TEXT NOT NULL,
    status TEXT NOT NULL,
    input TEXT NOT NULL,
    output TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    latency_ms INTEGER,
    token_usage INTEGER,
    error TEXT,
    correlation_id TEXT NOT NULL
  )`,
  `CREATE INDEX IF NOT EXISTS agent_executions_mission_time_idx ON agent_executions (mission_id, started_at)`,
  `CREATE INDEX IF NOT EXISTS agent_executions_agent_time_idx ON agent_executions (agent_id, started_at)`,
  `CREATE INDEX IF NOT EXISTS agent_executions_status_time_idx ON agent_executions (status, started_at)`,
  `CREATE INDEX IF NOT EXISTS agent_executions_tool_time_idx ON agent_executions (tool_name, started_at)`,
  `CREATE UNIQUE INDEX IF NOT EXISTS agent_executions_correlation_uidx ON agent_executions (correlation_id)`,
  `PRAGMA optimize`,
] as const;

const initializationByDatabase = new WeakMap<object, Promise<void>>();
let fallbackIdempotencySequence = 0;

const parseJson = <T>(value: unknown): T => {
  if (typeof value === "string") return JSON.parse(value) as T;
  return value as T;
};

const stableFingerprint = async (value: unknown): Promise<string> => {
  const bytes = new TextEncoder().encode(stableAgentToolStringify(value));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
};

const newIdempotencyKey = (): string => {
  if (typeof crypto.randomUUID === "function") return `agent-tool-${crypto.randomUUID()}`;
  fallbackIdempotencySequence += 1;
  return `agent-tool-${Date.now().toString(36)}-${fallbackIdempotencySequence.toString(36)}`;
};

async function initialize(database: D1Database): Promise<void> {
  const identity = database as unknown as object;
  const existing = initializationByDatabase.get(identity);
  if (existing) return existing;

  const initializing = database
    .batch(CREATE_STATEMENTS.map((statement) => database.prepare(statement)))
    .then(() => undefined)
    .catch((error: unknown) => {
      initializationByDatabase.delete(identity);
      throw error;
    });
  initializationByDatabase.set(identity, initializing);
  return initializing;
}

function inputPayload(execution: AgentToolExecution): AgentExecutionInputPayload {
  return {
    schemaVersion: "windops.agent-tool-input.v1",
    idempotencyKey: execution.idempotencyKey,
    requestFingerprint: execution.requestFingerprint,
    request: execution.request,
  };
}

function outputPayload(execution: AgentToolExecution): AgentExecutionOutputPayload {
  return {
    schemaVersion: "windops.agent-tool-output.v1",
    result: execution.result,
    tokenEstimate: execution.tokenEstimate,
    deterministic: true,
  };
}

function rowToExecution(row: AgentExecutionRow): AgentToolExecution {
  const input = parseJson<AgentExecutionInputPayload>(row.input);
  const output = parseJson<AgentExecutionOutputPayload>(row.output);
  return Object.freeze({
    executionId: row.id,
    agentId: row.agent_id,
    missionId: row.mission_id,
    idempotencyKey: input.idempotencyKey,
    requestFingerprint: input.requestFingerprint,
    correlationId: row.correlation_id,
    request: input.request,
    result: output.result,
    startedAt: row.started_at,
    completedAt: row.completed_at ?? row.started_at,
    status: row.status as AgentToolExecution["status"],
    latencyMs: row.latency_ms ?? 0,
    tokenEstimate: output.tokenEstimate ?? {
      input: 0,
      output: row.token_usage ?? 0,
      total: row.token_usage ?? 0,
      method: "utf8-bytes-div-4",
    },
    deterministic: true,
  });
}

async function readByExecutionId(
  database: D1Database,
  executionId: string,
): Promise<AgentToolExecution | null> {
  const row = await database
    .prepare(`SELECT * FROM agent_executions WHERE id = ? LIMIT 1`)
    .bind(executionId)
    .first<AgentExecutionRow>();
  return row ? rowToExecution(row) : null;
}

function idempotencyReplay(
  prior: AgentToolExecution,
  idempotencyKey: string,
  fingerprint: string,
): AgentToolExecution {
  if (prior.idempotencyKey !== idempotencyKey || prior.requestFingerprint !== fingerprint) {
    throw new AgentExecutionStoreError(
      "IDEMPOTENCY_KEY_REUSED",
      "This idempotency key was already used for a different Agent Tool request.",
      409,
      { idempotencyKey },
    );
  }
  return prior;
}

function seedAgentStatement(database: D1Database, agentId: string): D1PreparedStatement {
  const agent = agents.find((candidate) => candidate.id === agentId);
  if (!agent) {
    throw new AgentExecutionStoreError("AGENT_NOT_FOUND", `Agent ${agentId} was not found.`, 422, {
      agentId,
    });
  }
  return database
    .prepare(
      `INSERT OR IGNORE INTO agents (
        id, name, layer, role, status, model, prompt_version, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      agent.id,
      agent.name,
      agent.layer,
      agent.role,
      agent.status,
      agent.model,
      agent.promptVersion,
      windFarm.lastUpdatedAt,
      agent.lastActiveAt,
    );
}

function contextSeedStatements(
  database: D1Database,
  agentId: string,
  missionId: string | null,
): D1PreparedStatement[] {
  const statements: D1PreparedStatement[] = [];
  if (missionId) {
    const mission = missions.find((candidate) => candidate.id === missionId);
    if (!mission) {
      throw new AgentExecutionStoreError(
        "MISSION_NOT_FOUND",
        `Mission ${missionId} was not found.`,
        422,
        { missionId },
      );
    }
    const turbine = turbines.find((candidate) => candidate.id === mission.turbineId);
    if (!turbine) {
      throw new AgentExecutionStoreError(
        "MISSION_CONTEXT_INVALID",
        `Mission ${missionId} references an unavailable turbine.`,
        503,
        { missionId, turbineId: mission.turbineId },
      );
    }
    statements.push(
      database
        .prepare(
          `INSERT OR IGNORE INTO wind_farms (
            id, code, name, location, total_capacity_mw, status, created_at, updated_at
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
        )
        .bind(
          windFarm.id,
          windFarm.code,
          windFarm.name,
          windFarm.location,
          windFarm.totalCapacityMW,
          windFarm.status,
          windFarm.commissionedAt,
          windFarm.lastUpdatedAt,
        ),
      database
        .prepare(
          `INSERT OR IGNORE INTO wind_turbines (
            id, farm_id, model, serial_number, rated_power_mw, status,
            health_score, created_at, updated_at
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        )
        .bind(
          turbine.id,
          turbine.farmId,
          turbine.model,
          turbine.serialNumber,
          turbine.ratedPowerMW,
          turbine.status,
          turbine.healthScore,
          turbine.lastMaintenanceAt,
          windFarm.lastUpdatedAt,
        ),
      seedAgentStatement(database, mission.leadAgentId),
    );
    if (mission.leadAgentId !== agentId) statements.push(seedAgentStatement(database, agentId));
    statements.push(
      database
        .prepare(
          `INSERT OR IGNORE INTO missions (
            id, turbine_id, title, severity, status, progress_percent,
            lead_agent_id, diagnosis, confidence_percent, correlation_id,
            created_at, updated_at
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        )
        .bind(
          mission.id,
          mission.turbineId,
          mission.title,
          mission.severity,
          mission.status,
          mission.progressPercent,
          mission.leadAgentId,
          mission.diagnosis,
          mission.confidencePercent,
          `MISSION-${mission.id}`,
          mission.createdAt,
          mission.updatedAt,
        ),
    );
    return statements;
  }
  statements.push(seedAgentStatement(database, agentId));
  return statements;
}

function isConstraintError(error: unknown): boolean {
  return error instanceof Error && /constraint|unique|primary key/i.test(error.message);
}

function memoryReplay(idempotencyKey: string, fingerprint: string): AgentToolExecution | null {
  const prior = getAgentToolExecutionHistory().find(
    (execution) => execution.idempotencyKey === idempotencyKey,
  );
  return prior ? idempotencyReplay(prior, idempotencyKey, fingerprint) : null;
}

export async function executeAgentToolWithLedger(
  database: D1Database | undefined,
  write: AgentExecutionWriteRequest,
): Promise<AgentExecutionWriteResult> {
  if (write.persist && !database) {
    throw new AgentExecutionStoreError(
      "AUDIT_PERSISTENCE_UNAVAILABLE",
      "Agent Tool execution requires the Cloudflare D1 DB binding. Set persist=false only for an explicit non-durable demo run.",
      503,
    );
  }

  const idempotencyKey = write.idempotencyKey ?? newIdempotencyKey();
  const fingerprint = await stableFingerprint({
    agentId: write.agentId,
    missionId: write.missionId,
    request: write.request,
  });
  const executionId = `AGEXEC-${(await stableFingerprint(idempotencyKey)).toUpperCase()}`;
  const correlationId = `WOPS-${write.request.tool.toUpperCase()}-${executionId}`;

  if (!write.persist) {
    const prior = memoryReplay(idempotencyKey, fingerprint);
    if (prior) {
      return { execution: prior, persistence: "runtime-memory", replayed: true };
    }
    const execution = executeAgentTool(write.request, {
      executionId,
      agentId: write.agentId,
      missionId: write.missionId,
      idempotencyKey,
      requestFingerprint: fingerprint,
      correlationId,
      workflowSnapshot: write.workflowSnapshot,
    });
    return { execution, persistence: "runtime-memory", replayed: false };
  }

  const durableDatabase = database!;
  await initialize(durableDatabase);
  const prior = await readByExecutionId(durableDatabase, executionId);
  if (prior) {
    return {
      execution: idempotencyReplay(prior, idempotencyKey, fingerprint),
      persistence: "d1",
      replayed: true,
    };
  }

  const execution = executeAgentTool(write.request, {
    executionId,
    agentId: write.agentId,
    missionId: write.missionId,
    idempotencyKey,
    requestFingerprint: fingerprint,
    correlationId,
    recordInMemory: false,
    workflowSnapshot: write.workflowSnapshot,
  });
  const statements = contextSeedStatements(durableDatabase, write.agentId, write.missionId);
  statements.push(
    durableDatabase
      .prepare(
        `INSERT INTO agent_executions (
          id, mission_id, agent_id, tool_name, status, input, output,
          started_at, completed_at, latency_ms, token_usage, error, correlation_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      )
      .bind(
        execution.executionId,
        execution.missionId,
        execution.agentId,
        execution.request.tool,
        execution.status,
        JSON.stringify(inputPayload(execution)),
        JSON.stringify(outputPayload(execution)),
        execution.startedAt,
        execution.completedAt,
        execution.latencyMs,
        execution.tokenEstimate.total,
        execution.result.ok ? null : JSON.stringify(execution.result.error),
        execution.correlationId,
      ),
  );

  try {
    await durableDatabase.batch(statements);
  } catch (error) {
    if (isConstraintError(error)) {
      const replay = await readByExecutionId(durableDatabase, executionId);
      if (replay) {
        return {
          execution: idempotencyReplay(replay, idempotencyKey, fingerprint),
          persistence: "d1",
          replayed: true,
        };
      }
    }
    throw new AgentExecutionStoreError(
      "AGENT_EXECUTION_STORAGE_ERROR",
      "The Agent Tool execution could not be written to the D1 audit ledger.",
      503,
    );
  }

  return { execution, persistence: "d1", replayed: false };
}

function matchesMemoryFilter(
  execution: AgentToolExecution,
  filters: AgentExecutionFilters,
): boolean {
  return (
    (!filters.agentId || execution.agentId === filters.agentId) &&
    (!filters.missionId || execution.missionId === filters.missionId) &&
    (!filters.status || execution.status === filters.status) &&
    (!filters.toolName || execution.request.tool === filters.toolName)
  );
}

export async function readAgentToolLedger(
  database: D1Database | undefined,
  filters: AgentExecutionFilters,
): Promise<AgentExecutionReadResult> {
  if (!database) {
    const matching = getAgentToolExecutionHistory().filter((execution) =>
      matchesMemoryFilter(execution, filters),
    );
    return {
      executions: matching.slice(-filters.limit),
      total: matching.length,
      persistence: "runtime-memory",
    };
  }

  await initialize(database);
  const predicates: string[] = [];
  const bindings: (string | number)[] = [];
  if (filters.agentId) {
    predicates.push("agent_id = ?");
    bindings.push(filters.agentId);
  }
  if (filters.missionId) {
    predicates.push("mission_id = ?");
    bindings.push(filters.missionId);
  }
  if (filters.status) {
    predicates.push("status = ?");
    bindings.push(filters.status);
  }
  if (filters.toolName) {
    predicates.push("tool_name = ?");
    bindings.push(filters.toolName);
  }
  const where = predicates.length > 0 ? ` WHERE ${predicates.join(" AND ")}` : "";
  const [rowsResult, countRow] = await Promise.all([
    database
      .prepare(`SELECT * FROM agent_executions${where} ORDER BY started_at DESC, id DESC LIMIT ?`)
      .bind(...bindings, filters.limit)
      .all<AgentExecutionRow>(),
    database
      .prepare(`SELECT COUNT(*) AS count FROM agent_executions${where}`)
      .bind(...bindings)
      .first<{ readonly count: number }>(),
  ]);
  return {
    executions: rowsResult.results.map(rowToExecution).reverse(),
    total: Number(countRow?.count ?? 0),
    persistence: "d1",
  };
}
