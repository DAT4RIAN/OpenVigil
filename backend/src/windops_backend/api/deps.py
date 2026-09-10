import hashlib
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from hmac import compare_digest
from math import ceil
from typing import Any, cast
from uuid import uuid4

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from windops_backend.access_control import (
    access_scope_audit,
    attach_access_policy,
    data_scope_allowed,
    has_business_scope,
)
from windops_backend.config import IdentityAccessScope, Settings
from windops_backend.identity import (
    DelegatedIdentityAuthenticator,
    IdentityRoleError,
    InvalidIdentityError,
)
from windops_backend.knowledge_graph.domain import GraphAccessPolicy
from windops_backend.knowledge_graph.projection import ProjectionLimits
from windops_backend.knowledge_graph.store import KnowledgeGraphStore
from windops_backend.models import (
    AgentExecution,
    DelegatedRequestAudit,
    DelegatedRequestNonce,
    ReadAccessAudit,
)
from windops_backend.outbox import (
    KNOWLEDGE_GRAPH_PROJECTION_REQUESTED,
    mark_dispatched,
    pending_event_ids_by_type,
    process_knowledge_graph_projection_event,
)
from windops_backend.services.models import (
    ModelInferenceClient,
)
from windops_backend.storage import ArtifactVerifier

bearer_scheme = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)
DELEGATED_REPLAY_PROTECTED_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
DELEGATED_NONCE_CLEANUP_BATCH = 500
HUMAN_BUSINESS_ROLES = frozenset(
    {
        "operations_manager",
        "operations_approver",
        "maintenance_reviewer",
        "field_technician",
    }
)
MACHINE_ROLES = frozenset({"scada_ingestor", "eam_integrator"})
ALLOWED_TWIN_CONTENT_TYPES = frozenset(
    {
        "model/gltf+json",
        "model/gltf-binary",
        "application/octet-stream",
        "application/zip",
    }
)
MAX_TWIN_ARTIFACT_BYTES = 200 * 1024 * 1024


class Principal(BaseModel):
    subject: str
    email: str | None = None
    roles: tuple[str, ...]
    tenant_ids: tuple[str, ...] = ()
    wind_farm_ids: tuple[str, ...] = ()
    turbine_ids: tuple[str, ...] = ()
    entity_ids: tuple[str, ...] = ()
    data_scopes: tuple[str, ...] = ()
    allow_global: bool = False
    scope_configured: bool = False
    unrestricted: bool = False

    @property
    def role(self) -> str:
        return self.roles[0]

    def graph_access_policy(self) -> GraphAccessPolicy:
        return GraphAccessPolicy.from_values(
            tenant_ids=self.tenant_ids,
            wind_farm_ids=self.wind_farm_ids,
            turbine_ids=self.turbine_ids,
            entity_ids=self.entity_ids,
            data_scopes=self.data_scopes,
            allow_global=self.allow_global,
            unrestricted=self.unrestricted,
        )


async def _drain_or_dispatch_graph_projection_events(request: Request, settings: Settings) -> None:
    factory = cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)
    event_ids = await pending_event_ids_by_type(factory, KNOWLEDGE_GRAPH_PROJECTION_REQUESTED)
    if not event_ids:
        return
    if settings.outbox_inline_drain:
        store = cast(KnowledgeGraphStore, request.app.state.knowledge_graph_store)
        for event_id in event_ids:
            await process_knowledge_graph_projection_event(
                factory,
                event_id,
                store,
                ProjectionLimits.from_settings(settings),
            )
        return
    from windops_backend.workers import dispatch_graph_event_ids

    dispatch_graph_event_ids(event_ids)
    await mark_dispatched(factory, event_ids)


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[max(0, ceil(len(ordered) * 0.95) - 1)]


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return normalized.isoformat()


def _utc_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _token_total(execution: AgentExecution) -> int:
    value = execution.token_usage.get("total_tokens", 0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "UNAUTHENTICATED", "message": "Authentication required"},
        headers={"WWW-Authenticate": "Bearer"},
    )


def _split_scope_header(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _principal_from_subject(
    settings: Settings,
    request: Request,
    *,
    subject: str,
    roles: tuple[str, ...],
    email: str | None = None,
) -> Principal:
    configured_scope: IdentityAccessScope | None = settings.identity_scope_mappings.get(subject)
    scope_headers = {
        "tenant_ids": request.headers.get("x-windops-test-tenant-ids"),
        "wind_farm_ids": request.headers.get("x-windops-test-wind-farm-ids"),
        "turbine_ids": request.headers.get("x-windops-test-turbine-ids"),
        "entity_ids": request.headers.get("x-windops-test-entity-ids"),
        "data_scopes": request.headers.get("x-windops-test-data-scopes"),
    }
    has_test_scope_headers = any(value is not None for value in scope_headers.values())
    if has_test_scope_headers and not settings.test_auth_bypass_enabled:
        # These headers are deliberately test-only.  A production request can
        # never provide an alternate scope alongside its delegated identity.
        has_test_scope_headers = False

    if has_test_scope_headers:
        values = {key: _split_scope_header(value) for key, value in scope_headers.items()}
        allow_global = request.headers.get("x-windops-test-allow-global", "").lower() == "true"
        scope_configured = True
    elif configured_scope is not None:
        values = {
            "tenant_ids": tuple(configured_scope.tenant_ids),
            "wind_farm_ids": tuple(configured_scope.wind_farm_ids),
            "turbine_ids": tuple(configured_scope.turbine_ids),
            "entity_ids": tuple(configured_scope.entity_ids),
            "data_scopes": tuple(configured_scope.data_scopes),
        }
        allow_global = configured_scope.allow_global
        scope_configured = True
    else:
        values = {
            "tenant_ids": (),
            "wind_farm_ids": (),
            "turbine_ids": (),
            "entity_ids": (),
            "data_scopes": (),
        }
        allow_global = False
        scope_configured = False

    # Legacy development/static-token flows and the test system retain their
    # local all-data behavior.  Production delegated identities must have an
    # explicit mapping; otherwise graph reads fail closed.
    unrestricted = "test_system" in roles or (
        not scope_configured and settings.environment.value != "production"
    )
    return Principal(
        subject=subject,
        email=email,
        roles=roles,
        **values,
        allow_global=allow_global,
        scope_configured=scope_configured,
        unrestricted=unrestricted,
    )


async def get_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Principal:
    settings = get_runtime_settings(request)
    if settings.test_auth_bypass_enabled:
        subject = request.headers.get("x-windops-test-principal", "").strip()
        role = request.headers.get("x-windops-test-role", "").strip()
        if not subject or not role:
            raise _authentication_error()
        return _principal_from_subject(
            settings,
            request,
            subject=subject,
            roles=(role,),
        )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _authentication_error()
    supplied = credentials.credentials
    role_keys = [
        (f"ingest-source:{source_id}", "scada_ingestor", source_key)
        for source_id, source_key in settings.ingest_source_api_keys.items()
    ]
    if settings.environment.value != "production":
        role_keys.append(("scada-ingestor", "scada_ingestor", settings.scada_ingest_api_key))
    if settings.eam_webhook_api_key.get_secret_value():
        role_keys.append(("eam-integrator", "eam_integrator", settings.eam_webhook_api_key))
    if settings.auth_mode == "static_tokens":
        role_keys.extend(
            [
                (
                    "operations-approver",
                    "operations_approver",
                    settings.operations_approver_api_key,
                ),
                (
                    "maintenance-reviewer",
                    "maintenance_reviewer",
                    settings.maintenance_reviewer_api_key,
                ),
                (
                    "operations-manager",
                    "operations_manager",
                    settings.operations_manager_api_key,
                ),
                (
                    "field-technician",
                    "field_technician",
                    settings.field_technician_api_key,
                ),
            ]
        )
    for subject, role, configured in role_keys:
        if compare_digest(supplied, configured.get_secret_value()):
            return _principal_from_subject(
                settings,
                request,
                subject=subject,
                roles=(role,),
            )
    if settings.auth_mode != "sites_delegation":
        raise _authentication_error()
    authenticator = cast(DelegatedIdentityAuthenticator, request.app.state.identity_authenticator)
    request_body = await request.body()
    request_target = request.url.path
    if request.url.query:
        request_target = f"{request_target}?{request.url.query}"
    try:
        identity = authenticator.authenticate(
            supplied,
            request_method=request.method,
            request_target=request_target,
            body_sha256=hashlib.sha256(request_body).hexdigest(),
        )
    except IdentityRoleError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "No WindOps role is assigned"},
        ) from exc
    except InvalidIdentityError as exc:
        raise _authentication_error() from exc
    if request.method.upper() in DELEGATED_REPLAY_PROTECTED_METHODS:
        await _consume_delegated_write_nonce(
            request,
            subject=identity.subject,
            delegation_id=identity.delegation_id,
            expires_at=identity.expires_at,
            body_sha256=hashlib.sha256(request_body).hexdigest(),
            clock_skew_seconds=settings.delegation_clock_skew_seconds,
        )
    return _principal_from_subject(
        settings,
        request,
        subject=identity.subject,
        email=identity.email,
        roles=identity.roles,
    )


def _record_delegated_security_metric(request: Request, outcome: str) -> None:
    request.app.state.observability.delegated_write_security_events.labels(outcome=outcome).inc()


async def _write_delegated_replay_audit(
    factory: async_sessionmaker[AsyncSession],
    *,
    jti_sha256: str,
    subject: str,
    method: str,
    target: str,
) -> None:
    async with factory() as session, session.begin():
        session.add(
            DelegatedRequestAudit(
                id=str(uuid4()),
                jti_sha256=jti_sha256,
                subject=subject,
                method=method,
                target=target,
                outcome="replayed",
            )
        )


async def _consume_delegated_write_nonce(
    request: Request,
    *,
    subject: str,
    delegation_id: str,
    expires_at: datetime,
    body_sha256: str,
    clock_skew_seconds: int,
) -> None:
    """Consume one delegated write assertion in a transaction independent of business work."""

    factory = cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)
    method = request.method.upper()
    target = request.url.path
    if request.url.query:
        target = f"{target}?{request.url.query}"
    jti_sha256 = hashlib.sha256(delegation_id.encode("utf-8")).hexdigest()
    now = datetime.now(UTC)
    retain_until = expires_at + timedelta(seconds=clock_skew_seconds + 1)
    try:
        async with factory() as session, session.begin():
            expired = (
                select(DelegatedRequestNonce.jti_sha256)
                .where(DelegatedRequestNonce.expires_at < now)
                .limit(DELEGATED_NONCE_CLEANUP_BATCH)
            )
            await session.execute(
                delete(DelegatedRequestNonce).where(DelegatedRequestNonce.jti_sha256.in_(expired))
            )
            session.add(
                DelegatedRequestNonce(
                    jti_sha256=jti_sha256,
                    subject=subject,
                    method=method,
                    target=target,
                    body_sha256=body_sha256,
                    expires_at=retain_until,
                )
            )
            session.add(
                DelegatedRequestAudit(
                    id=str(uuid4()),
                    jti_sha256=jti_sha256,
                    subject=subject,
                    method=method,
                    target=target,
                    outcome="accepted",
                )
            )
            await session.flush()
    except IntegrityError as exc:
        try:
            await _write_delegated_replay_audit(
                factory,
                jti_sha256=jti_sha256,
                subject=subject,
                method=method,
                target=target,
            )
        except SQLAlchemyError:
            logger.exception(
                "delegated write replay audit persistence failed",
                extra={"subject": subject, "method": method, "target": target},
            )
        _record_delegated_security_metric(request, "replayed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "DELEGATED_IDENTITY_REPLAYED",
                "message": "The delegated write assertion has already been consumed",
            },
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except SQLAlchemyError as exc:
        _record_delegated_security_metric(request, "store_failure")
        logger.exception(
            "delegated write replay store unavailable; request failed closed",
            extra={"subject": subject, "method": method, "target": target},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "DELEGATION_REPLAY_STORE_UNAVAILABLE",
                "message": "Delegated write verification is temporarily unavailable",
            },
        ) from exc
    _record_delegated_security_metric(request, "accepted")


def require_roles(*allowed_roles: str) -> Any:
    async def authorize(
        request: Request,
        principal: Principal = Depends(get_principal),
        session: AsyncSession = Depends(get_session),
    ) -> Principal:
        if "test_system" not in principal.roles and set(principal.roles).isdisjoint(allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "FORBIDDEN", "message": "Insufficient role"},
            )
        if set(principal.roles).intersection(MACHINE_ROLES):
            # Machine identities are authorized only by their dedicated route
            # role dependency. They never inherit access to business reads.
            session.sync_session.info.pop("windops_access_policy", None)
            return principal
        policy = _require_business_scope(principal)
        _require_endpoint_data_scope(request, policy)
        attach_access_policy(session, policy)
        return principal

    return authorize


def require_global_roles(
    *allowed_roles: str,
    data_scopes: str | tuple[str, ...] = "platform",
) -> Any:
    """Require an unbounded, explicit global grant for global control-plane writes."""

    async def authorize(
        principal: Principal = Depends(require_roles(*allowed_roles)),
    ) -> Principal:
        policy = principal.graph_access_policy()
        restricted_entities = policy.entity_ids and "*" not in policy.entity_ids
        if not policy.unrestricted and (
            not policy.allow_global
            or restricted_entities
            or not data_scope_allowed(policy, data_scopes)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "GLOBAL_SCOPE_REQUIRED",
                    "message": "An explicit unbounded global grant is required",
                },
            )
        return principal

    return authorize


APPROVAL_ROLES = {
    "approve": "operations_approver",
    "reject": "operations_approver",
    "request_revision": "maintenance_reviewer",
    "escalate": "operations_manager",
}


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)
    async with factory() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise


def get_runtime_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_artifact_verifier(request: Request) -> ArtifactVerifier:
    return cast(ArtifactVerifier, request.app.state.artifact_verifier)


def get_model_inference_client(request: Request) -> ModelInferenceClient:
    return cast(ModelInferenceClient, request.app.state.model_inference_client)


async def require_read_access(
    request: Request,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_session),
) -> Principal:
    """Authenticate and durably attribute every business read to a server-owned subject."""

    if "test_system" not in principal.roles and set(principal.roles).isdisjoint(
        HUMAN_BUSINESS_ROLES
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "BUSINESS_READ_FORBIDDEN",
                "message": "This machine identity cannot access business read APIs",
            },
        )
    policy = _require_business_scope(principal)
    _require_endpoint_data_scope(request, policy)
    attach_access_policy(session, policy)

    query: dict[str, object] = {
        key: request.query_params.getlist(key) for key in request.query_params.keys()
    }
    query["_authorization"] = access_scope_audit(policy)
    session.add(
        ReadAccessAudit(
            id=str(uuid4()),
            subject=principal.subject,
            role=",".join(principal.roles),
            method=request.method,
            endpoint=request.url.path,
            query=query,
        )
    )
    await session.commit()
    return principal


def _require_business_scope(principal: Principal) -> GraphAccessPolicy:
    policy = principal.graph_access_policy()
    if not principal.unrestricted and (
        not principal.scope_configured or not has_business_scope(policy)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "BUSINESS_SCOPE_REQUIRED",
                "message": "An explicit tenant, asset, entity, or global grant is required",
            },
        )
    return policy


def _require_endpoint_data_scope(request: Request, policy: GraphAccessPolicy) -> None:
    required = _endpoint_data_scopes(request.url.path)
    if required is None or data_scope_allowed(policy, required):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "DATA_SCOPE_FORBIDDEN",
            "message": "The identity is not granted access to this business data domain",
        },
    )


def _endpoint_data_scopes(path: str) -> tuple[str, ...] | None:
    normalized = path.casefold()
    if normalized == "/api/v1/session":
        # Session bootstrap reports only server-owned roles/capabilities. It
        # must work for any valid business scope before a domain request runs.
        return None
    if normalized.startswith("/api/v1/events"):
        # Event rows are classified and filtered per aggregate type.
        return None
    if normalized.startswith("/api/v1/knowledge-graph"):
        # Graph nodes carry their own per-node data scopes and are filtered by
        # GraphAccessPolicy after the explicit graph-scope dependency.
        return None
    rules: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
        (("/api/v1/knowledge",), ("knowledge",)),
        (("/api/v1/turbines/",), ("asset",)),
        (("/api/v1/scada",), ("telemetry",)),
        (("/api/v1/ingest/sources",), ("platform",)),
        (("/api/v1/alarms",), ("alarm",)),
        (("/api/v1/missions", "/api/v1/diagnoses", "/api/v1/maintenance-plans"), ("mission",)),
        (("/api/v1/decisions",), ("decision",)),
        (("/api/v1/work-orders",), ("work_order",)),
        (("/api/v1/resources",), ("resource",)),
        (("/api/v1/benchmarks",), ("benchmark",)),
        (("/api/v1/models", "/api/v1/predictive-assessments"), ("model",)),
        (("/api/v1/reports",), ("report",)),
        (("/api/v1/platform", "/api/v1/data-catalog"), ("platform",)),
        (
            (
                "/api/v1/agents",
                "/api/v1/agent-tools",
                "/api/v1/agent-executions",
                "/api/v1/observability",
                "/api/v1/tools",
                "/api/v1/catalog",
            ),
            ("agent",),
        ),
        (("/api/v1/health", "/api/v1/digital-twin", "/api/v1/turbines"), ("asset",)),
        (("/api/v1/dashboard",), ("dashboard",)),
    )
    for prefixes, scopes in rules:
        if normalized.startswith(prefixes):
            # Turbine SCADA is telemetry, not a generic asset read.
            if normalized.startswith("/api/v1/turbines/") and normalized.endswith("/scada"):
                return ("telemetry",)
            return scopes
    # A newly added authenticated endpoint fails closed for identities that
    # deliberately carry a restricted data-domain grant.
    return ("__unclassified__",)


async def require_knowledge_graph_read_access(
    principal: Principal = Depends(require_read_access),
) -> Principal:
    """Require an explicit graph scope before any graph data is read."""

    policy = principal.graph_access_policy()
    has_asset_grant = bool(
        policy.tenant_ids or policy.wind_farm_ids or policy.turbine_ids or policy.entity_ids
    )
    if (
        not principal.scope_configured
        or (not principal.unrestricted and not has_asset_grant and not policy.allow_global)
    ) and not principal.unrestricted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "GRAPH_SCOPE_REQUIRED",
                "message": (
                    "An explicit tenant, wind-farm, turbine, or graph data grant is required"
                ),
            },
        )
    return principal


def _event_cursor(after: int, last_event_id: str | None) -> int:
    if last_event_id is None or not last_event_id.strip():
        return after
    try:
        parsed = int(last_event_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_EVENT_CURSOR", "message": "Last-Event-ID must be an integer"},
        ) from exc
    if parsed < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_EVENT_CURSOR", "message": "Event cursor cannot be negative"},
        )
    return max(after, parsed)
