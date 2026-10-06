import asyncio
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.errors import InvalidTransitionError
from windops_backend.model_base import utcnow
from windops_backend.model_structural import (
    HealthBaseline,
    ModalObservation,
    StructuralAnalysisRun,
    TowerComponent,
    WaveformRecord,
)
from windops_backend.schema_structural import BaselineCreate
from windops_backend.services.idempotency import canonical_request_hash
from windops_backend.services.structural import asset_scope, related, save_identity, serialize
from windops_backend.structural_baseline import fit_environmental_baseline, measurement_signature


async def publish_baseline(
    session: AsyncSession, payload: BaselineCreate, subject: str
) -> dict[str, Any]:
    scope = await asset_scope(session, payload.turbine_id)
    await related(session, TowerComponent, payload.component_id, payload.turbine_id)
    if payload.valid_until <= utcnow():
        raise InvalidTransitionError("baseline expiry must be in the future")
    rows = []
    for identity in payload.training_modal_ids:
        modal = await related(session, ModalObservation, identity, payload.turbine_id)
        run = await related(session, StructuralAnalysisRun, modal.run_id, payload.turbine_id)
        record = await related(session, WaveformRecord, run.record_id, payload.turbine_id)
        if run.status != "succeeded" or not (run.result or {}).get("quality", {}).get("usable"):
            raise InvalidTransitionError(
                "baseline training requires successful quality-approved analysis"
            )
        if "rotor_harmonics_unchecked" in (run.result or {}).get("warnings", []):
            raise InvalidTransitionError("baseline training requires checked rotor harmonics")
        if any(s["component_id"] != payload.component_id for s in record.channel_snapshot):
            raise InvalidTransitionError("baseline channels must belong to the requested component")
        raw_run, raw_record = serialize(run), serialize(record)
        rows.append(
            {
                **serialize(modal),
                "record_id": record.id,
                "started_at": raw_record["started_at"],
                "ended_at": raw_record["ended_at"],
                "environment": record.environment,
                "source_kind": record.source_kind,
                "artifact_sha256": record.artifact_sha256,
                "signature": measurement_signature(raw_run, raw_record),
            }
        )
    reference = next(r for r in rows if r["id"] == payload.reference_modal_id)
    try:
        model = await asyncio.to_thread(
            fit_environmental_baseline,
            rows,
            reference,
            list(payload.features),
            payload.minimum_mac,
            payload.maximum_relative_frequency_shift,
            payload.screening_sigma,
        )
    except ValueError as exc:
        raise InvalidTransitionError(str(exc)) from exc
    if datetime.fromisoformat(model["training_window"]["end"]) >= payload.valid_until:
        raise InvalidTransitionError("baseline validity must cover the training period")
    return await save_identity(
        session,
        HealthBaseline(
            **scope,
            component_id=payload.component_id,
            code=payload.code,
            revision=payload.revision,
            confirmation_reference=payload.confirmation_reference,
            reference_modal_id=payload.reference_modal_id,
            training_modal_ids=payload.training_modal_ids,
            source_kind=reference["source_kind"],
            input_fingerprint=canonical_request_hash(
                {"request": payload.model_dump(mode="json"), "model": model}
            ),
            model=model,
            created_by=subject,
            valid_until=payload.valid_until,
        ),
    )
