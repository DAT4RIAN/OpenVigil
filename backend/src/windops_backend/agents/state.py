from typing import Any, NotRequired, TypedDict


class PublicWorkflowState(TypedDict):
    """Only auditable/public workflow artifacts; hidden chain-of-thought is never represented."""

    mission_id: str
    turbine_id: str
    alarm_id: str
    analysis_profile: NotRequired[dict[str, Any]]
    workflow_status: str
    evidence: list[dict[str, Any]]
    diagnosis: NotRequired[dict[str, Any]]
    alternatives: NotRequired[list[dict[str, Any]]]
    decision_id: NotRequired[str]
    reviews: NotRequired[list[dict[str, Any]]]
    requires_human_approval: NotRequired[bool]
    approved: NotRequired[bool]
    approval_id: NotRequired[str]
    work_order_id: NotRequired[str]
    resource_reservation_ids: NotRequired[list[str]]
    resume_from: NotRequired[str]
