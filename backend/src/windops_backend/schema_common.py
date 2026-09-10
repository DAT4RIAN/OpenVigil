from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


# Owned declarations follow; their order is part of the compatibility contract.
class ErrorBody(BaseModel):
    code: str
    message: str


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AgentExecutionOut(OrmModel):
    id: str
    mission_id: str
    node: str
    agent_role: str
    status: str
    input_refs: dict[str, Any]
    public_output: dict[str, Any]
    tool_calls: list[dict[str, Any]]
    latency_ms: int
    provider: str
    model: str | None
    token_usage: dict[str, Any]
    error_code: str | None
    started_at: datetime
    completed_at: datetime | None
