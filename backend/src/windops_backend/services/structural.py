"""Governed structural acquisition; no scientific calculation occurs in HTTP."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.errors import ConflictError, InvalidTransitionError, NotFoundError
from windops_backend.model_structural import (
    PrestressObservation,
    SensorChannel,
    StructuralAnalysisRun,
    TendonAssembly,
    TowerComponent,
    WaveformRecord,
)
from windops_backend.models import Turbine, WindFarm
from windops_backend.schema_structural import (
    AnalysisCreate,
    ComponentCreate,
    DirectForceArtifact,
    PrestressCreate,
    SensorCreate,
    TendonCreate,
    WaveformCreate,
    aware,
)
from windops_backend.services.events import append_domain_event
from windops_backend.services.idempotency import canonical_request_hash
from windops_backend.storage import ArtifactVerifier, OutboxEvent
from windops_backend.structural_contract import ANALYSIS_CONTRACT_VERSION, algorithm_identity

STRUCTURAL_ANALYSIS_REQUESTED = "structural.analysis.requested"
STRUCTURAL_CONTENT_TYPES = frozenset({"application/json"})
MAX_STRUCTURAL_BYTES = 32 * 1024 * 1024


def artifact_prefix(turbine_id: str) -> str:
    return f"structural/turbines/{turbine_id}"


async def asset_scope(session: AsyncSession, turbine_id: str) -> dict[str, str]:
    turbine = await session.get(Turbine, turbine_id)
    if turbine is None:
        raise NotFoundError("structural asset was not found")
    # Turbine authorization was already enforced by its ORM loader criteria.
    # Read only that farm's tenant identity; a turbine grant must not expose
    # sibling farm metadata through an unrestricted ORM farm read.
    tenant_id = await session.scalar(
        select(WindFarm.__table__.c.tenant_id).where(
            WindFarm.__table__.c.id == turbine.wind_farm_id
        )
    )
    if tenant_id is None:
        raise NotFoundError("structural wind farm was not found")
    return {"tenant_id": tenant_id, "wind_farm_id": turbine.wind_farm_id, "turbine_id": turbine.id}


async def related(session: AsyncSession, model: Any, identity: str, turbine_id: str) -> Any:
    row = await session.get(model, identity)
    if row is None or row.turbine_id != turbine_id:
        raise NotFoundError("structural reference was not found within this asset")
    return row


def serialize(row: Any) -> dict[str, Any]:
    values = {c.name: getattr(row, c.name) for c in row.__table__.columns}
    return dict(
        jsonable_encoder(
            {
                name: aware(value) if isinstance(value, datetime) else value
                for name, value in values.items()
            }
        )
    )


async def save_identity(session: AsyncSession, row: Any) -> dict[str, Any]:
    try:
        async with session.begin_nested():
            session.add(row)
            await session.flush()
    except IntegrityError as exc:
        raise ConflictError("this asset code and revision already exist") from exc
    append_domain_event(
        session,
        event_type="structural.identity.created",
        aggregate_type="turbine",
        aggregate_id=row.turbine_id,
        payload={"turbine_id": row.turbine_id, "entity_id": row.id, "kind": row.__tablename__},
    )
    return serialize(row)


async def create_component(
    session: AsyncSession, payload: ComponentCreate, subject: str
) -> dict[str, Any]:
    scope = await asset_scope(session, payload.turbine_id)
    if payload.parent_id:
        await related(session, TowerComponent, payload.parent_id, payload.turbine_id)
    return await save_identity(
        session,
        TowerComponent(**payload.model_dump(exclude={"turbine_id"}), **scope, created_by=subject),
    )


async def create_tendon(
    session: AsyncSession, payload: TendonCreate, subject: str
) -> dict[str, Any]:
    scope = await asset_scope(session, payload.turbine_id)
    await related(session, TowerComponent, payload.component_id, payload.turbine_id)
    return await save_identity(
        session,
        TendonAssembly(**payload.model_dump(exclude={"turbine_id"}), **scope, created_by=subject),
    )


async def create_sensor(
    session: AsyncSession, payload: SensorCreate, subject: str
) -> dict[str, Any]:
    scope = await asset_scope(session, payload.turbine_id)
    await related(session, TowerComponent, payload.component_id, payload.turbine_id)
    if payload.tendon_id:
        tendon = await related(session, TendonAssembly, payload.tendon_id, payload.turbine_id)
        if tendon.component_id != payload.component_id:
            raise InvalidTransitionError("sensor and tendon must reference the same component")
    return await save_identity(
        session,
        SensorChannel(**payload.model_dump(exclude={"turbine_id"}), **scope, created_by=subject),
    )


async def verified_input(
    verifier: ArtifactVerifier, bucket: str, turbine_id: str, uri: str, sha256: str
) -> bytes:
    try:
        content, _ = await verifier.read_verified_object(
            uri,
            sha256,
            bucket=bucket,
            prefix=artifact_prefix(turbine_id),
            allowed_content_types=STRUCTURAL_CONTENT_TYPES,
            max_bytes=MAX_STRUCTURAL_BYTES,
        )
    except ValueError as exc:
        raise InvalidTransitionError(str(exc)) from exc
    return content


async def register_waveform(
    session: AsyncSession,
    payload: WaveformCreate,
    subject: str,
    verifier: ArtifactVerifier,
    bucket: str,
) -> dict[str, Any]:
    scope = await asset_scope(session, payload.turbine_id)
    channels = [
        await related(session, SensorChannel, channel_id, payload.turbine_id)
        for channel_id in payload.channel_ids
    ]
    request = payload.model_dump(mode="json")
    request["artifact_sha256"] = payload.artifact_sha256.lower()
    fingerprint = canonical_request_hash(
        {
            **request,
            # URI is a transport location; identical content/acquisition is deduplicated.
            "artifact_uri": None,
        }
    )
    # Location validation is also mandatory for an existing content fingerprint.
    await verified_input(
        verifier, bucket, payload.turbine_id, payload.artifact_uri, payload.artifact_sha256
    )
    existing = await session.scalar(
        select(WaveformRecord).where(
            WaveformRecord.turbine_id == payload.turbine_id,
            WaveformRecord.input_fingerprint == fingerprint,
        )
    )
    if existing:
        return serialize(existing)
    # The worker parses the signal and its quality after this registration.
    row = WaveformRecord(
        **scope,
        **payload.model_dump(exclude={"turbine_id", "artifact_sha256", "environment"}),
        artifact_sha256=payload.artifact_sha256.lower(),
        environment=payload.environment.model_dump(mode="json"),
        channel_snapshot=[serialize(channel) for channel in channels],
        input_fingerprint=fingerprint,
        created_by=subject,
    )
    try:
        async with session.begin_nested():
            session.add(row)
            await session.flush()
    except IntegrityError:
        existing = await session.scalar(
            select(WaveformRecord).where(
                WaveformRecord.turbine_id == payload.turbine_id,
                WaveformRecord.input_fingerprint == fingerprint,
            )
        )
        if existing is None:
            raise
        return serialize(existing)
    append_domain_event(
        session,
        event_type="structural.record.registered",
        aggregate_type="turbine",
        aggregate_id=row.turbine_id,
        payload={"record_id": row.id, "turbine_id": row.turbine_id, "source_kind": row.source_kind},
    )
    return serialize(row)


async def submit_analysis(
    session: AsyncSession,
    payload: AnalysisCreate,
    subject: str,
    *,
    deployment: dict[str, str] | None = None,
) -> dict[str, Any]:
    record = await session.get(WaveformRecord, payload.record_id)
    if record is None:
        raise NotFoundError("structural record was not found")
    scope = await asset_scope(session, record.turbine_id)
    identity = algorithm_identity()
    if deployment is not None:
        identity["deployment_declared"] = dict(deployment)
    fingerprint = canonical_request_hash(
        {
            "record": record.input_fingerprint,
            **payload.model_dump(mode="json"),
            "contract": ANALYSIS_CONTRACT_VERSION,
            "algorithm_identity": identity,
        }
    )
    existing = await session.scalar(
        select(StructuralAnalysisRun).where(
            StructuralAnalysisRun.turbine_id == record.turbine_id,
            StructuralAnalysisRun.input_fingerprint == fingerprint,
        )
    )
    if existing:
        return serialize(existing)
    row = StructuralAnalysisRun(
        id=str(uuid4()),
        **scope,
        record_id=record.id,
        method=payload.method,
        config=payload.config.model_dump(),
        algorithm_identity=identity,
        input_fingerprint=fingerprint,
        created_by=subject,
    )
    try:
        async with session.begin_nested():
            session.add(row)
            await session.flush()
            session.add(
                OutboxEvent(
                    event_type=STRUCTURAL_ANALYSIS_REQUESTED,
                    aggregate_type="structural_analysis",
                    aggregate_id=row.id,
                    payload={"run_id": row.id, "turbine_id": row.turbine_id},
                )
            )
            await session.flush()
    except IntegrityError:
        existing = await session.scalar(
            select(StructuralAnalysisRun).where(
                StructuralAnalysisRun.turbine_id == record.turbine_id,
                StructuralAnalysisRun.input_fingerprint == fingerprint,
            )
        )
        if existing is None:
            raise
        return serialize(existing)
    append_domain_event(
        session,
        event_type="structural.analysis.requested",
        aggregate_type="turbine",
        aggregate_id=row.turbine_id,
        payload={"run_id": row.id, "turbine_id": row.turbine_id},
    )
    return serialize(row)


async def register_prestress(
    session: AsyncSession,
    payload: PrestressCreate,
    subject: str,
    verifier: ArtifactVerifier,
    bucket: str,
) -> dict[str, Any]:
    scope = await asset_scope(session, payload.turbine_id)
    await related(session, TendonAssembly, payload.tendon_id, payload.turbine_id)
    sensor = await related(session, SensorChannel, payload.sensor_id, payload.turbine_id)
    if sensor.quantity != "force" or sensor.tendon_id != payload.tendon_id:
        raise InvalidTransitionError("direct force measurement needs the tendon's force sensor")
    content = await verified_input(
        verifier, bucket, payload.turbine_id, payload.artifact_uri, payload.artifact_sha256
    )
    try:
        artifact = DirectForceArtifact.model_validate_json(content)
    except (ValueError, ValidationError) as exc:
        raise InvalidTransitionError("direct force artifact is invalid") from exc
    if (
        artifact.tendon_id != sensor.tendon_id
        or artifact.sensor_id != sensor.id
        or artifact.calibration_version != sensor.calibration_version
        or artifact.unit != sensor.unit
    ):
        raise InvalidTransitionError("direct measurement identity, unit or calibration mismatch")
    if not (
        aware(sensor.calibration_at) <= artifact.observed_at < aware(sensor.calibration_valid_until)
    ):
        raise InvalidTransitionError("direct force measurement is outside its calibration validity")
    if not sensor.range_min <= artifact.value <= sensor.range_max:
        raise InvalidTransitionError("direct force measurement is outside the calibrated range")
    value_kn = artifact.value / 1000 if artifact.unit == "N" else artifact.value
    fingerprint = canonical_request_hash(
        {
            "turbine_id": payload.turbine_id,
            "sha256": payload.artifact_sha256.lower(),
            "source_kind": payload.source_kind,
        }
    )
    existing = await session.scalar(
        select(PrestressObservation).where(
            PrestressObservation.turbine_id == payload.turbine_id,
            PrestressObservation.input_fingerprint == fingerprint,
        )
    )
    if existing:
        return serialize(existing)
    row = PrestressObservation(
        **scope,
        tendon_id=sensor.tendon_id,
        sensor_id=sensor.id,
        observed_at=artifact.observed_at,
        value_kn=value_kn,
        calibration_version=sensor.calibration_version,
        artifact_uri=payload.artifact_uri,
        artifact_sha256=payload.artifact_sha256.lower(),
        source_kind=payload.source_kind,
        input_fingerprint=fingerprint,
        uncertainty={
            "status": "quantified" if artifact.uncertainty_kn is not None else "unquantified",
            "absolute_kn": artifact.uncertainty_kn,
            "source": "measurement_artifact",
        },
        created_by=subject,
    )
    try:
        async with session.begin_nested():
            session.add(row)
            await session.flush()
    except IntegrityError:
        existing = await session.scalar(
            select(PrestressObservation).where(
                PrestressObservation.turbine_id == payload.turbine_id,
                PrestressObservation.input_fingerprint == fingerprint,
            )
        )
        if existing is None:
            raise
        return serialize(existing)
    append_domain_event(
        session,
        event_type="structural.prestress.registered",
        aggregate_type="turbine",
        aggregate_id=row.turbine_id,
        payload={"observation_id": row.id, "turbine_id": row.turbine_id},
    )
    return serialize(row)


def prestress_page_trends(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in items:
        key = (row["tendon_id"], row["sensor_id"], row["calibration_version"], row["source_kind"])
        groups.setdefault(key, []).append(row)
    results = []
    for (tendon_id, sensor_id, calibration_version, source_kind), rows in groups.items():
        ordered = sorted(rows, key=lambda row: (row["observed_at"], row["id"]))
        comparable = len(ordered) >= 2 and ordered[-1]["observed_at"] > ordered[0]["observed_at"]
        results.append(
            {
                "tendon_id": tendon_id,
                "sensor_id": sensor_id,
                "calibration_version": calibration_version,
                "source_kind": source_kind,
                "scope": "returned_page_only",
                "measurement_method": "direct_force_v1",
                "unit": "kN",
                "status": "raw_change_available" if comparable else "insufficient_windows",
                "change_kn": ordered[-1]["value_kn"] - ordered[0]["value_kn"]
                if comparable
                else None,
                "points": [
                    {
                        "observation_id": r["id"],
                        "observed_at": r["observed_at"],
                        "value_kn": r["value_kn"],
                        "artifact_sha256": r["artifact_sha256"],
                        "uncertainty": r["uncertainty"],
                    }
                    for r in ordered
                ],
                "uncertainty_status": "not_combined",
                "environmental_compensation": "unavailable",
                "engineering_status": "requires_engineering_review",
                "loss_percentage": None,
            }
        )
    return results
