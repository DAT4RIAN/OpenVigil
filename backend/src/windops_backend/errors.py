class DomainError(Exception):
    code = "DOMAIN_ERROR"
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    code = "NOT_FOUND"
    status_code = 404


class ConflictError(DomainError):
    code = "REVISION_CONFLICT"
    status_code = 409


class IdempotencyConflictError(DomainError):
    code = "IDEMPOTENCY_KEY_REUSED"
    status_code = 409


class ApprovalGateError(DomainError):
    code = "APPROVAL_REQUIRED"
    status_code = 403


class KnowledgeScopeError(DomainError):
    code = "FORBIDDEN"
    status_code = 403


class InvalidTransitionError(DomainError):
    code = "INVALID_TRANSITION"
    status_code = 422


class KnowledgeGraphUnavailableError(DomainError):
    code = "KNOWLEDGE_GRAPH_UNAVAILABLE"
    status_code = 503
