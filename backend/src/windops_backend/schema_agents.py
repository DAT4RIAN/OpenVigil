from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from windops_backend.schema_operations import MissionCreateRequest


# Owned declarations follow; their order is part of the compatibility contract.
class AgentControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["start", "stop"]
    expected_definition_id: str = Field(min_length=3, max_length=96)
    reason: str = Field(min_length=3, max_length=500)


class AgentReleaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_definition_id: str = Field(min_length=3, max_length=96)
    version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
    display_name: str = Field(min_length=3, max_length=160)
    role: str = Field(pattern=r"^[a-z][a-z0-9_]{2,95}$")
    description: str = Field(min_length=3, max_length=4000)
    reason: str = Field(min_length=3, max_length=500)


class AgentToolExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    tool: Literal[
        "get_turbine_status",
        "query_scada",
        "query_alarm_history",
        "query_vibration",
        "query_weather",
        "query_maintenance_history",
        "query_similar_failures",
        "calculate_health_score",
        "assess_condition_evidence",
        "create_decision",
        "create_work_order",
        "query_manual",
        "query_work_orders",
        "query_spare_parts",
        "query_crew",
        "query_vessels",
        "update_work_order",
    ]
    args: dict[str, Any]
    agent_id: str | None = Field(default=None, alias="agentId", min_length=3, max_length=96)
    mission_id: str | None = Field(default=None, alias="missionId", min_length=3, max_length=40)
    idempotency_key: str | None = Field(
        default=None, alias="idempotencyKey", min_length=8, max_length=128
    )
    persist: bool = True


class MissionCommentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=4000)


class MissionBatchCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    missions: list[MissionCreateRequest] = Field(min_length=1, max_length=20)

    @field_validator("missions")
    @classmethod
    def unique_alarm_ids(cls, value: list[MissionCreateRequest]) -> list[MissionCreateRequest]:
        if len({item.alarm_id for item in value}) != len(value):
            raise ValueError("batch mission alarm_id values must be unique")
        return value
