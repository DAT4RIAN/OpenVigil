from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# Owned declarations follow; their order is part of the compatibility contract.
class ReportGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_type: Literal[
        "daily-operations",
        "alarm-analysis",
        "ai-diagnosis",
        "maintenance",
        "asset-health",
        "weekly-wind-farm",
    ]
    period: Literal["daily", "weekly", "incident", "snapshot"]
    reason: str = Field(min_length=3, max_length=500)
