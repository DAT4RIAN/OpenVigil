from enum import StrEnum


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class TurbineStatus(StrEnum):
    RUNNING = "running"
    WARNING = "warning"
    MAINTENANCE = "maintenance"
    OFFLINE = "offline"


class AlarmSeverity(StrEnum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    WARNING = "warning"
    INFO = "info"


class AlarmStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class MissionStatus(StrEnum):
    DETECTED = "detected"
    INVESTIGATING = "investigating"
    DIAGNOSED = "diagnosed"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    REJECTED = "rejected"


class ApprovalAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_REVISION = "request_revision"
    ESCALATE = "escalate"


class WorkOrderStatus(StrEnum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class TaskStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"


class ExecutionStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ResourceStatus(StrEnum):
    AVAILABLE = "available"
    RESERVED = "reserved"


class DecisionStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISION_REQUESTED = "revision_requested"
