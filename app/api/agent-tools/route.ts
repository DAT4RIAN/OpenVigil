import {
  AgentToolRuntimeError,
  agentToolCatalog,
  executeAgentTool,
  getAgentToolExecutionHistory,
  windFarm,
} from "@/lib";

import { jsonResponse } from "../_shared";

const apiMeta = (extra: Readonly<Record<string, unknown>> = {}) => ({
  snapshotAt: windFarm.lastUpdatedAt,
  deterministic: true,
  persisted: false,
  historyScope: "runtime-memory-demo-only",
  catalogCount: agentToolCatalog.length,
  ...extra,
});

const errorResponse = (
  code: string,
  message: string,
  status: number,
  details: Readonly<Record<string, unknown>> | null = null,
  data: unknown = null,
): Response =>
  jsonResponse(
    {
      ok: false,
      data,
      error: { code, message, details },
      meta: apiMeta({ historyCount: getAgentToolExecutionHistory().length }),
    },
    status,
  );

export function GET(): Response {
  const executionHistory = getAgentToolExecutionHistory();
  return jsonResponse({
    ok: true,
    data: {
      catalog: agentToolCatalog,
      executionHistory,
    },
    error: null,
    meta: apiMeta({ historyCount: executionHistory.length }),
  });
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
      "Request body must be an object with tool and args.",
      400,
    );
  }

  const requestBody = body as Record<string, unknown>;
  if (typeof requestBody.tool !== "string" || requestBody.tool.trim().length === 0) {
    return errorResponse("INVALID_REQUEST", "tool must be a non-empty string.", 400, {
      argument: "tool",
    });
  }

  try {
    const execution = executeAgentTool({
      tool: requestBody.tool.trim(),
      args: requestBody.args,
    });

    if (!execution.result.ok) {
      return errorResponse(
        execution.result.error.code,
        execution.result.error.message,
        execution.result.error.statusCode,
        execution.result.error.details,
        { execution },
      );
    }

    return jsonResponse({
      ok: true,
      data: { execution },
      error: null,
      meta: apiMeta({
        historyCount: getAgentToolExecutionHistory().length,
        dryRun: execution.result.dryRun,
      }),
    });
  } catch (error) {
    if (error instanceof AgentToolRuntimeError) {
      return errorResponse(error.code, error.message, error.statusCode, error.details);
    }
    return errorResponse("AGENT_TOOL_RUNTIME_ERROR", "The agent tool runtime failed.", 500);
  }
}
