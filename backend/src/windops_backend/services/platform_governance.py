from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.config import TelemetrySourcePolicy, TelemetryVariablePolicy
from windops_backend.errors import ConflictError, InvalidTransitionError, NotFoundError
from windops_backend.models import (
    AssetTwinProfile,
    DataContractDefinition,
    IngestSource,
    IngestSourceSecurityAudit,
    Mission,
    MissionComment,
    PlatformConfigurationRevision,
    PlatformConfigurationSecurityAudit,
    Resource,
    ResourceReservation,
    Turbine,
    WeatherWindow,
    WorkOrder,
)
from windops_backend.platform_configuration import (
    PLATFORM_CONFIGURATION_SCHEMA_VERSION,
    PlatformConfigurationValidationError,
    inspect_platform_configuration_material,
    validate_platform_configuration_value,
    validate_secret_manager_reference,
)
from windops_backend.schemas import (
    AssetTwinProfileRequest,
    DataContractCreateRequest,
    IngestSourcePolicyRequest,
    PlatformConfigurationCreateRequest,
    PlatformConfigurationRotationConfirmationRequest,
    ResourceReassignRequest,
    ResourceStockAdjustRequest,
    WorkOrderScheduleUpdateRequest,
)
from windops_backend.services.eam import enqueue_eam_work_order_publish
from windops_backend.services.events import append_domain_event
from windops_backend.services.ingest import ensure_ingest_source


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _same_instant(left: datetime, right: datetime) -> bool:
    return _as_utc(left) == _as_utc(right)


async def create_mission_comment(
    session: AsyncSession,
    *,
    mission_id: str,
    body: str,
    subject: str,
    email: str | None,
) -> MissionComment:
    if await session.get(Mission, mission_id) is None:
        raise NotFoundError(f"mission {mission_id} was not found")
    comment = MissionComment(
        id=str(uuid4()),
        mission_id=mission_id,
        body=body.strip(),
        author_subject=subject,
        author_email=email,
    )
    session.add(comment)
    append_domain_event(
        session,
        event_type="mission.comment.created",
        aggregate_type="mission",
        aggregate_id=mission_id,
        payload={
            "comment_id": comment.id,
            "mission_id": mission_id,
            "author_subject": subject,
        },
    )
    await session.flush()
    return comment


async def upsert_ingest_source_policy(
    session: AsyncSession,
    request: IngestSourcePolicyRequest,
    *,
    subject: str,
) -> IngestSource:
    validated_secret_reference = (
        validate_secret_manager_reference(request.secret_reference)
        if request.secret_reference is not None
        else None
    )
    existing = await session.get(IngestSource, request.source_id, with_for_update=True)
    if existing is not None:
        if request.expected_updated_at is None:
            raise ConflictError("expected_updated_at is required when updating a data source")
        if not _same_instant(existing.updated_at, request.expected_updated_at):
            raise ConflictError("the data source changed; refresh before retrying")
    elif request.expected_updated_at is not None:
        raise ConflictError("expected_updated_at must be omitted when creating a data source")
    policy = TelemetrySourcePolicy.model_validate(
        request.model_dump(
            exclude={"source_id", "secret_reference", "expected_updated_at", "reason"}
        )
    )
    source = await ensure_ingest_source(session, request.source_id, policy)
    source.credential_secret_reference = validated_secret_reference
    append_domain_event(
        session,
        event_type="ingest.source.configured",
        aggregate_type="ingest_source",
        aggregate_id=source.id,
        payload={
            "source_id": source.id,
            "source_kind": source.source_kind,
            "enabled": source.enabled,
            "has_secret_reference": source.credential_secret_reference is not None,
            "reason": request.reason,
            "subject": subject,
        },
    )
    await session.flush()
    return source


async def create_data_contract(
    session: AsyncSession,
    request: DataContractCreateRequest,
    *,
    subject: str,
) -> DataContractDefinition:
    source = await session.get(IngestSource, request.source_id, with_for_update=True)
    if source is None:
        raise NotFoundError(f"ingest source {request.source_id} was not found")
    contract = TelemetryVariablePolicy.model_validate(request.contract).model_dump(mode="json")
    latest = await session.scalar(
        select(DataContractDefinition)
        .where(
            DataContractDefinition.source_id == request.source_id,
            DataContractDefinition.variable == request.variable,
        )
        .order_by(desc(DataContractDefinition.revision))
        .with_for_update()
        .limit(1)
    )
    current_revision = latest.revision if latest is not None else 0
    if request.expected_revision != current_revision:
        raise ConflictError("the data contract changed; refresh before retrying")
    if latest is not None:
        latest.active = False
    revision = DataContractDefinition(
        id=str(uuid4()),
        source_id=request.source_id,
        variable=request.variable,
        revision=current_revision + 1,
        contract=contract,
        reason=request.reason,
        created_by=subject,
    )
    session.add(revision)
    policy = TelemetrySourcePolicy.model_validate(source.policy)
    variable_contracts = dict(policy.variable_contracts)
    variable_contracts[request.variable] = TelemetryVariablePolicy.model_validate(contract)
    source.policy = policy.model_copy(update={"variable_contracts": variable_contracts}).model_dump(
        mode="json"
    )
    source.updated_at = datetime.now(UTC)
    append_domain_event(
        session,
        event_type="data.contract.activated",
        aggregate_type="data_contract",
        aggregate_id=revision.id,
        payload={
            "source_id": request.source_id,
            "variable": request.variable,
            "revision": revision.revision,
            "reason": request.reason,
            "subject": subject,
        },
    )
    await session.flush()
    return revision


def _validate_platform_configuration(
    request: PlatformConfigurationCreateRequest,
) -> dict[str, Any]:
    try:
        return validate_platform_configuration_value(
            request.configuration_key,
            request.value,
            secret_reference=request.secret_reference,
            reason=request.reason,
        )
    except PlatformConfigurationValidationError as exc:
        raise InvalidTransitionError(str(exc)) from exc


async def create_platform_configuration_revision(
    session: AsyncSession,
    request: PlatformConfigurationCreateRequest,
    *,
    subject: str,
) -> PlatformConfigurationRevision:
    canonical_value = _validate_platform_configuration(request)
    try:
        async with session.begin_nested():
            latest = await session.scalar(
                select(PlatformConfigurationRevision)
                .where(PlatformConfigurationRevision.configuration_key == request.configuration_key)
                .order_by(desc(PlatformConfigurationRevision.revision))
                .with_for_update()
                .limit(1)
            )
            current_revision = latest.revision if latest is not None else 0
            if request.expected_revision != current_revision:
                raise ConflictError("the platform configuration changed; refresh before retrying")
            if latest is not None:
                latest.active = False
            revision = PlatformConfigurationRevision(
                id=str(uuid4()),
                configuration_key=request.configuration_key,
                revision=current_revision + 1,
                value=canonical_value,
                schema_version=PLATFORM_CONFIGURATION_SCHEMA_VERSION,
                secret_reference=request.secret_reference,
                security_status="clean",
                reason=request.reason,
                created_by=subject,
            )
            session.add(revision)
            append_domain_event(
                session,
                event_type="platform.configuration.activated",
                aggregate_type="platform_configuration",
                aggregate_id=revision.id,
                payload={
                    "configuration_key": revision.configuration_key,
                    "revision": revision.revision,
                    "has_secret_reference": revision.secret_reference is not None,
                    "reason": revision.reason,
                    "subject": subject,
                },
            )
            await session.flush()
    except IntegrityError as exc:
        # SELECT .. FOR UPDATE cannot lock an absent first revision.  The
        # database uniqueness constraint is therefore the authoritative race
        # arbiter; contain its failure in the savepoint and expose a retryable
        # domain conflict without poisoning the caller's outer transaction.
        raise ConflictError("the platform configuration changed; refresh before retrying") from exc
    return revision


def serialize_platform_configuration_revision(
    revision: PlatformConfigurationRevision,
) -> dict[str, object] | None:
    """Return a verified secret-free representation or quarantine it from the response."""

    if revision.security_status != "clean":
        return None
    try:
        value = validate_platform_configuration_value(
            revision.configuration_key,
            revision.value,
            secret_reference=revision.secret_reference,
            reason=revision.reason,
        )
    except PlatformConfigurationValidationError:
        return None
    return {
        "configuration_key": revision.configuration_key,
        "revision": revision.revision,
        "schema_version": revision.schema_version,
        "value": value,
        "secret_configured": revision.secret_reference is not None,
        "reason": revision.reason,
        "created_by": revision.created_by,
        "created_at": revision.created_at,
    }


def _configuration_fingerprint(revision: PlatformConfigurationRevision) -> str:
    serialized = json.dumps(
        {
            "configuration_key": revision.configuration_key,
            "revision": revision.revision,
            "value": revision.value,
            "secret_reference": revision.secret_reference,
            "reason": revision.reason,
        },
        ensure_ascii=False,
        allow_nan=True,
        default=str,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _secret_fingerprint(value: str) -> str:
    """Fingerprint secret-bearing material without retaining the submitted value."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def remediate_ingest_source_credentials(session: AsyncSession) -> int:
    """Quarantine legacy ingest credentials that are not strict Secret Manager references."""

    remediated = 0
    after_id = ""
    while True:
        sources = list(
            (
                await session.scalars(
                    select(IngestSource)
                    .where(
                        IngestSource.id > after_id,
                        IngestSource.credential_secret_reference.is_not(None),
                    )
                    .order_by(IngestSource.id)
                    .limit(200)
                    .with_for_update()
                    .execution_options(skip_windops_access_control=True)
                )
            ).all()
        )
        if not sources:
            break
        after_id = sources[-1].id
        for source in sources:
            reference = source.credential_secret_reference
            if reference is None:
                continue
            try:
                validate_secret_manager_reference(reference)
            except PlatformConfigurationValidationError:
                fingerprint = _secret_fingerprint(reference)
                existing = await session.scalar(
                    select(IngestSourceSecurityAudit)
                    .where(
                        IngestSourceSecurityAudit.source_id == source.id,
                        IngestSourceSecurityAudit.original_fingerprint == fingerprint,
                    )
                    .execution_options(skip_windops_access_control=True)
                )
                if existing is not None:
                    continue
                source.credential_secret_reference = None
                source.enabled = False
                source.status = "quarantined"
                session.add(
                    IngestSourceSecurityAudit(
                        id=str(uuid4()),
                        source_id=source.id,
                        finding_categories=["invalid_secret_reference"],
                        original_fingerprint=fingerprint,
                        action="quarantined_and_redacted",
                        rotation_required=True,
                    )
                )
                remediated += 1
        await session.flush()
    return remediated


async def remediate_platform_configuration_history(session: AsyncSession) -> int:
    """Quarantine unsafe historical rows without persisting findings or submitted values."""

    remediated = 0
    after_id = ""
    while True:
        revisions = list(
            (
                await session.scalars(
                    select(PlatformConfigurationRevision)
                    .where(PlatformConfigurationRevision.id > after_id)
                    .order_by(PlatformConfigurationRevision.id)
                    .limit(200)
                    .with_for_update()
                )
            ).all()
        )
        if not revisions:
            break
        after_id = revisions[-1].id
        for revision in revisions:
            if revision.security_status != "clean":
                continue
            categories: set[str] = set()
            rotation_required = False
            try:
                inspection = inspect_platform_configuration_material(
                    {revision.configuration_key: revision.value},
                    reason=revision.reason,
                )
                categories.update(inspection.finding_categories)
                if inspection.finding_categories:
                    rotation_required = True
            except PlatformConfigurationValidationError:
                categories.add("invalid_payload_limits")
            if revision.secret_reference is not None:
                try:
                    validate_secret_manager_reference(revision.secret_reference)
                except PlatformConfigurationValidationError:
                    categories.add("invalid_secret_reference")
                    rotation_required = True
            try:
                canonical = validate_platform_configuration_value(
                    revision.configuration_key,
                    revision.value,
                    secret_reference=revision.secret_reference,
                    reason=revision.reason,
                )
            except PlatformConfigurationValidationError:
                canonical = None
                if not categories:
                    categories.add("invalid_versioned_schema")

            if canonical is not None:
                revision.value = canonical
                revision.schema_version = PLATFORM_CONFIGURATION_SCHEMA_VERSION
                continue

            original_fingerprint = _configuration_fingerprint(revision)
            revision.value = {}
            revision.secret_reference = None
            revision.reason = "Security remediation removed the original configuration content."
            revision.active = False
            revision.security_status = (
                "quarantined_rotation_required" if rotation_required else "quarantined_invalid"
            )
            session.add(
                PlatformConfigurationSecurityAudit(
                    id=str(uuid4()),
                    configuration_id=revision.id,
                    configuration_key=revision.configuration_key,
                    revision=revision.revision,
                    finding_categories=sorted(categories),
                    original_fingerprint=original_fingerprint,
                    action="quarantined_and_redacted",
                    rotation_required=rotation_required,
                )
            )
            remediated += 1
        await session.flush()
    return remediated


async def unresolved_platform_configuration_rotations(session: AsyncSession) -> int:
    configuration_count = int(
        await session.scalar(
            select(func.count())
            .select_from(PlatformConfigurationSecurityAudit)
            .where(PlatformConfigurationSecurityAudit.rotation_required.is_(True))
            .execution_options(skip_windops_access_control=True)
        )
        or 0
    )
    source_count = int(
        await session.scalar(
            select(func.count())
            .select_from(IngestSourceSecurityAudit)
            .where(IngestSourceSecurityAudit.rotation_required.is_(True))
            .execution_options(skip_windops_access_control=True)
        )
        or 0
    )
    return configuration_count + source_count


async def confirm_ingest_source_rotation(
    session: AsyncSession,
    *,
    audit_id: str,
    replacement_secret_reference: str,
    rotation_evidence: str,
    subject: str,
) -> IngestSourceSecurityAudit:
    """Install a validated replacement reference and close one source audit."""

    audit = await session.scalar(
        select(IngestSourceSecurityAudit)
        .where(IngestSourceSecurityAudit.id == audit_id)
        .with_for_update()
        .execution_options(skip_windops_access_control=True)
    )
    if audit is None:
        raise NotFoundError(f"ingest source security audit {audit_id} was not found")
    replacement = validate_secret_manager_reference(replacement_secret_reference)
    if not audit.rotation_required:
        raise ConflictError("ingest source credential rotation is already confirmed")
    source = await session.scalar(
        select(IngestSource)
        .where(IngestSource.id == audit.source_id)
        .with_for_update()
        .execution_options(skip_windops_access_control=True)
    )
    if source is None:
        raise NotFoundError(f"ingest source {audit.source_id} was not found")
    source.credential_secret_reference = replacement
    source.enabled = True
    source.status = "never_seen"
    audit.replacement_secret_reference = replacement
    audit.rotation_evidence = rotation_evidence.strip()
    audit.rotation_confirmed_by = subject
    audit.rotation_confirmed_at = datetime.now(UTC)
    audit.rotation_required = False
    audit.action = "rotation_confirmed"
    append_domain_event(
        session,
        event_type="ingest.source.credential_rotation_confirmed",
        aggregate_type="ingest_source",
        aggregate_id=source.id,
        payload={
            "source_id": source.id,
            "audit_id": audit.id,
            "subject": subject,
            "rotation_evidence": audit.rotation_evidence,
        },
    )
    await session.flush()
    return audit


async def redacted_platform_configuration_status(session: AsyncSession) -> dict[str, object]:
    revisions = list(
        (
            await session.scalars(
                select(PlatformConfigurationRevision)
                .where(PlatformConfigurationRevision.active.is_(True))
                .order_by(PlatformConfigurationRevision.configuration_key)
                .limit(101)
                .execution_options(skip_windops_access_control=True)
            )
        ).all()
    )
    bounded = revisions[:100]
    verified = [
        serialized
        for revision in bounded
        if (serialized := serialize_platform_configuration_revision(revision)) is not None
    ]
    pending_rotations = await unresolved_platform_configuration_rotations(session)
    unsafe = len(revisions) > 100 or len(verified) != len(revisions)
    return {
        "status": "attention_required" if pending_rotations or unsafe else "ready",
        "configured_keys": sorted(str(row["configuration_key"]) for row in verified),
        "configuration_count": len(verified),
        "pending_credential_rotations": pending_rotations,
    }


async def platform_configuration_security_audits(
    session: AsyncSession,
) -> list[PlatformConfigurationSecurityAudit]:
    return list(
        (
            await session.scalars(
                select(PlatformConfigurationSecurityAudit).order_by(
                    PlatformConfigurationSecurityAudit.created_at.desc(),
                    PlatformConfigurationSecurityAudit.id.desc(),
                )
            )
        ).all()
    )


async def confirm_platform_configuration_rotation(
    session: AsyncSession,
    *,
    audit_id: str,
    request: PlatformConfigurationRotationConfirmationRequest,
    subject: str,
) -> PlatformConfigurationSecurityAudit:
    audit = await session.scalar(
        select(PlatformConfigurationSecurityAudit)
        .where(PlatformConfigurationSecurityAudit.id == audit_id)
        .with_for_update()
    )
    if audit is None:
        raise NotFoundError("platform configuration security audit was not found")
    # Keep the service boundary strict even when called outside FastAPI's
    # Pydantic request validation (for example, a migration or an operator
    # script).  Never persist a replacement URI that was only regex-checked.
    try:
        replacement_secret_reference = validate_secret_manager_reference(
            request.replacement_secret_reference
        )
    except PlatformConfigurationValidationError as exc:
        raise InvalidTransitionError(str(exc)) from exc
    if not audit.rotation_required:
        return audit
    audit.rotation_required = False
    audit.replacement_secret_reference = replacement_secret_reference
    audit.rotation_evidence = request.rotation_evidence
    audit.rotation_confirmed_by = subject
    audit.rotation_confirmed_at = datetime.now(UTC)
    revision = await session.get(
        PlatformConfigurationRevision,
        audit.configuration_id,
        with_for_update=True,
    )
    if revision is not None and revision.security_status == "quarantined_rotation_required":
        revision.security_status = "quarantined_rotation_confirmed"
    append_domain_event(
        session,
        event_type="platform.configuration.credential_rotation_confirmed",
        aggregate_type="platform_configuration",
        aggregate_id=audit.configuration_id,
        payload={
            "configuration_key": audit.configuration_key,
            "revision": audit.revision,
            "security_audit_id": audit.id,
            "subject": subject,
        },
    )
    await session.flush()
    return audit


async def upsert_asset_twin_profile(
    session: AsyncSession,
    *,
    turbine_id: str,
    request: AssetTwinProfileRequest,
    subject: str,
) -> AssetTwinProfile:
    if await session.get(Turbine, turbine_id) is None:
        raise NotFoundError(f"turbine {turbine_id} was not found")
    if not request.geometry_uri.startswith("minio://"):
        raise ConflictError("geometry_uri must use a governed minio:// object URI")
    profile = await session.get(AssetTwinProfile, turbine_id, with_for_update=True)
    if profile is None:
        if request.expected_updated_at is not None:
            raise ConflictError("expected_updated_at must be omitted when creating a twin profile")
        profile = AssetTwinProfile(
            turbine_id=turbine_id,
            manufacturer=request.manufacturer,
            latitude=request.latitude,
            longitude=request.longitude,
            elevation_m=request.elevation_m,
            coordinate_reference_system=request.coordinate_reference_system,
            geometry_uri=request.geometry_uri,
            geometry_sha256=request.geometry_sha256.lower(),
            updated_by=subject,
        )
        session.add(profile)
    else:
        if request.expected_updated_at is None:
            raise ConflictError("expected_updated_at is required when updating a twin profile")
        if not _same_instant(profile.updated_at, request.expected_updated_at):
            raise ConflictError("the twin profile changed; refresh before retrying")
        profile.manufacturer = request.manufacturer
        profile.latitude = request.latitude
        profile.longitude = request.longitude
        profile.elevation_m = request.elevation_m
        profile.coordinate_reference_system = request.coordinate_reference_system
        profile.geometry_uri = request.geometry_uri
        profile.geometry_sha256 = request.geometry_sha256.lower()
        profile.updated_by = subject
        profile.updated_at = datetime.now(UTC)
    append_domain_event(
        session,
        event_type="asset.twin-profile.updated",
        aggregate_type="turbine",
        aggregate_id=turbine_id,
        payload={
            "turbine_id": turbine_id,
            "coordinate_reference_system": profile.coordinate_reference_system,
            "geometry_sha256": profile.geometry_sha256,
            "reason": request.reason,
            "subject": subject,
        },
    )
    await session.flush()
    return profile


async def adjust_resource_stock(
    session: AsyncSession,
    *,
    resource_id: str,
    request: ResourceStockAdjustRequest,
    subject: str,
) -> Resource:
    resource = await session.get(Resource, resource_id, with_for_update=True)
    if resource is None:
        raise NotFoundError(f"resource {resource_id} was not found")
    if not _same_instant(resource.updated_at, request.expected_updated_at):
        raise ConflictError("the resource changed; refresh before retrying")
    reserved = int(
        await session.scalar(
            select(func.coalesce(func.sum(ResourceReservation.quantity), 0)).where(
                ResourceReservation.resource_id == resource_id
            )
        )
        or 0
    )
    next_quantity = resource.quantity + request.quantity_delta
    if next_quantity < reserved or next_quantity < 0:
        raise ConflictError("stock cannot fall below the governed reserved quantity")
    resource.quantity = next_quantity
    resource.status = "reserved" if next_quantity == reserved and reserved else "available"
    resource.updated_at = datetime.now(UTC)
    append_domain_event(
        session,
        event_type="resource.stock.adjusted",
        aggregate_type="resource",
        aggregate_id=resource.id,
        payload={
            "resource_id": resource.id,
            "quantity_delta": request.quantity_delta,
            "quantity": resource.quantity,
            "reserved": reserved,
            "reason": request.reason,
            "subject": subject,
        },
    )
    await session.flush()
    return resource


async def reassign_resource(
    session: AsyncSession,
    request: ResourceReassignRequest,
    *,
    subject: str,
    eam_enabled: bool,
) -> ResourceReservation:
    reservation = await session.scalar(
        select(ResourceReservation)
        .where(
            ResourceReservation.mission_id == request.mission_id,
            ResourceReservation.resource_id == request.from_resource_id,
        )
        .with_for_update()
    )
    if reservation is None:
        raise NotFoundError("the source resource reservation was not found")
    source = await session.get(Resource, request.from_resource_id, with_for_update=True)
    target = await session.get(Resource, request.to_resource_id, with_for_update=True)
    if source is None or target is None:
        raise NotFoundError("the requested resource was not found")
    if source.resource_type != target.resource_type:
        raise ConflictError("resource reassignment requires the same resource type")
    if target.status != "available" or target.quantity < reservation.quantity:
        raise ConflictError("the target resource is not available in the required quantity")
    existing = await session.scalar(
        select(ResourceReservation.id).where(
            ResourceReservation.mission_id == request.mission_id,
            ResourceReservation.resource_id == request.to_resource_id,
        )
    )
    if existing is not None:
        raise ConflictError("the target resource is already reserved by this mission")
    reservation.resource_id = target.id
    target.status = "reserved"
    target.updated_at = datetime.now(UTC)
    remaining_source_reservations = int(
        await session.scalar(
            select(func.count())
            .select_from(ResourceReservation)
            .where(
                ResourceReservation.resource_id == source.id,
                ResourceReservation.id != reservation.id,
            )
        )
        or 0
    )
    if remaining_source_reservations == 0:
        source.status = "available"
        source.updated_at = datetime.now(UTC)
    work_order = await session.scalar(
        select(WorkOrder).where(WorkOrder.mission_id == request.mission_id).with_for_update()
    )
    if work_order is not None:
        if target.resource_type == "crew":
            work_order.assigned_team = target.name
        work_order.updated_at = datetime.now(UTC)
        if eam_enabled:
            enqueue_eam_work_order_publish(session, work_order.id)
    append_domain_event(
        session,
        event_type="resource.reservation.reassigned",
        aggregate_type="mission",
        aggregate_id=request.mission_id,
        payload={
            "mission_id": request.mission_id,
            "from_resource_id": source.id,
            "to_resource_id": target.id,
            "reason": request.reason,
            "subject": subject,
        },
    )
    await session.flush()
    return reservation


async def update_work_order_schedule(
    session: AsyncSession,
    *,
    work_order_id: str,
    request: WorkOrderScheduleUpdateRequest,
    subject: str,
    eam_enabled: bool,
    dry_run: bool = False,
) -> WorkOrder:
    work_order = await session.get(WorkOrder, work_order_id, with_for_update=True)
    if work_order is None:
        raise NotFoundError(f"work order {work_order_id} was not found")
    if work_order.status in {"completed", "closed"}:
        raise ConflictError("a completed work order cannot be rescheduled")
    if not _same_instant(work_order.updated_at, request.expected_updated_at):
        raise ConflictError("the work order changed; refresh before retrying")
    turbine = await session.get(Turbine, work_order.turbine_id)
    if turbine is None:
        raise NotFoundError(f"turbine {work_order.turbine_id} was not found")
    weather = await session.scalar(
        select(WeatherWindow).where(
            WeatherWindow.wind_farm_id == turbine.wind_farm_id,
            WeatherWindow.suitable.is_(True),
            WeatherWindow.starts_at <= request.planned_start,
            WeatherWindow.ends_at >= request.deadline,
        )
    )
    if weather is None:
        raise ConflictError("no governed suitable weather window fully covers the schedule")
    if dry_run:
        return work_order
    work_order.planned_start = request.planned_start
    work_order.deadline = request.deadline
    if request.assigned_team is not None:
        work_order.assigned_team = request.assigned_team
    work_order.updated_at = datetime.now(UTC)
    if eam_enabled:
        enqueue_eam_work_order_publish(session, work_order.id)
    append_domain_event(
        session,
        event_type="work_order.schedule.updated",
        aggregate_type="work_order",
        aggregate_id=work_order.id,
        payload={
            "work_order_id": work_order.id,
            "planned_start": request.planned_start.isoformat(),
            "deadline": request.deadline.isoformat(),
            "assigned_team": work_order.assigned_team,
            "weather_window_id": weather.id,
            "reason": request.reason,
            "subject": subject,
        },
    )
    await session.flush()
    return work_order


async def active_platform_configurations(
    session: AsyncSession,
) -> list[PlatformConfigurationRevision]:
    rows = list(
        (
            await session.scalars(
                select(PlatformConfigurationRevision)
                .where(PlatformConfigurationRevision.active.is_(True))
                .order_by(PlatformConfigurationRevision.configuration_key)
            )
        ).all()
    )
    return rows


async def active_data_contracts(session: AsyncSession) -> list[DataContractDefinition]:
    return list(
        (
            await session.scalars(
                select(DataContractDefinition)
                .where(DataContractDefinition.active.is_(True))
                .order_by(DataContractDefinition.source_id, DataContractDefinition.variable)
            )
        ).all()
    )
