"""Build source-grounded cards and keep human claims separate from physical qualification."""

import hashlib
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.access_control import ACCESS_POLICY_SESSION_KEY
from windops_backend.config import Settings
from windops_backend.errors import ConflictError, InvalidTransitionError, NotFoundError
from windops_backend.knowledge_graph.domain import GraphAccessPolicy
from windops_backend.model_base import utcnow
from windops_backend.model_engineering_claim import EngineeringClaim, EngineeringClaimReview
from windops_backend.model_structural import (
    HealthBaseline,
    ModalObservation,
    PrestressObservation,
    SensorChannel,
    StructuralAnalysisRun,
    TendonAssembly,
    TowerComponent,
    WaveformRecord,
)
from windops_backend.models import KnowledgeDocument, KnowledgePassage, Mission
from windops_backend.schema_engineering_claim import (
    EngineeringClaimCreate,
    EngineeringClaimReviewRequest,
    EngineeringEvidenceCard,
    EngineeringEvidenceReference,
)
from windops_backend.schema_structural import aware
from windops_backend.services.events import append_domain_event
from windops_backend.services.idempotency import canonical_request_hash
from windops_backend.services.knowledge import (
    ALLOWED_KNOWLEDGE_CONTENT_TYPES,
    MAX_KNOWLEDGE_ARTIFACT_BYTES,
)
from windops_backend.services.knowledge_access import knowledge_document_query
from windops_backend.services.structural import (
    MAX_STRUCTURAL_BYTES,
    STRUCTURAL_CONTENT_TYPES,
    artifact_prefix,
    asset_scope,
    related,
    serialize,
)
from windops_backend.storage import ArtifactVerifier


async def build_evidence_card(
    session: AsyncSession,
    reference: EngineeringEvidenceReference,
    *,
    turbine_id: str,
    component_id: str,
) -> dict[str, Any]:
    component = await related(session, TowerComponent, component_id, turbine_id)
    scope = await asset_scope(session, turbine_id)
    card: dict[str, Any] = {
        "evidence_id": f"{reference.kind}:{reference.source_id}",
        "reference": reference.model_dump(mode="json"),
        **scope,
        "component_id": component_id,
        "time_window": {"start": None, "end": None},
        "source": {},
        "method": {},
        "measurements": [],
        "quality": {},
        "uncertainty": {"status": "unquantified"},
        "applicability": {},
        "valid_until": None,
    }
    if reference.kind in {"analysis", "modal"}:
        mode = None
        if reference.kind == "modal":
            mode = await related(session, ModalObservation, reference.source_id, turbine_id)
            run = await related(session, StructuralAnalysisRun, mode.run_id, turbine_id)
        else:
            run = await related(session, StructuralAnalysisRun, reference.source_id, turbine_id)
        record = await related(session, WaveformRecord, run.record_id, turbine_id)
        snapshots = record.channel_snapshot
        if not snapshots or any(row["component_id"] != component_id for row in snapshots):
            raise InvalidTransitionError("analysis channels do not belong to the claim component")
        if record.channel_ids != [row["id"] for row in snapshots]:
            raise InvalidTransitionError("analysis channel identities changed after acquisition")
        for snapshot in snapshots:
            sensor = await related(session, SensorChannel, snapshot["id"], turbine_id)
            if canonical_request_hash(serialize(sensor)) != canonical_request_hash(snapshot):
                raise InvalidTransitionError("analysis sensor version changed after acquisition")
        result = run.result or {}
        card.update(
            time_window={"start": aware(record.started_at), "end": aware(record.ended_at)},
            source={
                "artifact_uri": record.artifact_uri,
                "sha256": record.artifact_sha256,
                "source_kind": record.source_kind,
                "record_id": record.id,
                "run_id": run.id,
                "integrity": "verified_at_ingestion",
            },
            method={
                "name": run.method,
                "algorithm_identity": run.algorithm_identity,
                "config": run.config,
                "config_sha256": canonical_request_hash(run.config),
                "calibration": snapshots,
            },
            quality={
                **result.get("quality", {"usable": False, "exclusions": [run.status]}),
                "run_status": run.status,
                "error_code": run.error_code,
                "warnings": result.get("warnings", []),
            },
            applicability={
                "environment": record.environment,
                "source_reference": record.source_reference,
            },
            valid_until=min(
                aware(datetime.fromisoformat(row["calibration_valid_until"])) for row in snapshots
            ),
        )
        if mode is not None:
            card["measurements"] = [
                {"name": "frequency", "value": mode.frequency_hz, "unit": "Hz"},
                {"name": "damping_ratio", "value": None, "unit": "1"},
            ]
            card["quality"]["modal"] = mode.quality
            card["quality"]["usable"] = (
                bool(card["quality"].get("usable"))
                and mode.quality.get("status") == "candidate"
                and "rotor_harmonics_unchecked" not in card["quality"]["warnings"]
            )
            card["uncertainty"] = mode.uncertainty
            card["source"]["modal_id"] = mode.id
        else:
            card["quality"]["usable"] = (
                bool(card["quality"].get("usable")) and run.status == "succeeded"
            )
        card["method"]["absolute_prestress_available"] = False
    elif reference.kind == "prestress":
        measurement = await related(session, PrestressObservation, reference.source_id, turbine_id)
        sensor = await related(session, SensorChannel, measurement.sensor_id, turbine_id)
        tendon = await related(session, TendonAssembly, measurement.tendon_id, turbine_id)
        if sensor.component_id != component_id or tendon.component_id != component_id:
            raise InvalidTransitionError(
                "direct-force source does not belong to the claim component"
            )
        card.update(
            time_window={
                "start": aware(measurement.observed_at),
                "end": aware(measurement.observed_at),
            },
            source={
                "artifact_uri": measurement.artifact_uri,
                "sha256": measurement.artifact_sha256,
                "source_kind": measurement.source_kind,
                "tendon_id": tendon.id,
                "observation_id": measurement.id,
                "integrity": "verified_at_ingestion",
            },
            method={
                "name": "direct_force_v1",
                "sensor": serialize(sensor),
                "tendon_revision": tendon.revision,
            },
            measurements=[{"name": "direct_force", "value": measurement.value_kn, "unit": "kN"}],
            quality={
                "usable": measurement.calibration_version == sensor.calibration_version,
                "exclusions": [],
            },
            uncertainty=measurement.uncertainty,
            applicability={
                "tendon_id": tendon.id,
                "sensor_id": sensor.id,
                "boundary": tendon.boundary,
            },
            valid_until=aware(sensor.calibration_valid_until),
        )
    elif reference.kind == "baseline":
        baseline = await related(session, HealthBaseline, reference.source_id, turbine_id)
        if baseline.component_id != component_id:
            raise InvalidTransitionError("baseline does not belong to the claim component")
        card.update(
            source={
                "baseline_id": baseline.id,
                "sha256": baseline.input_fingerprint,
                "source_kind": baseline.source_kind,
            },
            method={
                "name": "confirmed_environmental_ols_v1",
                "revision": baseline.revision,
                "model": baseline.model,
            },
            quality={"usable": True, "exclusions": []},
            applicability={
                "confirmation_reference": baseline.confirmation_reference,
                "training_modal_ids": baseline.training_modal_ids,
            },
            uncertainty=baseline.model.get("uncertainty", {"status": "unquantified"}),
            valid_until=aware(baseline.valid_until),
        )
    else:
        passage = await session.get(KnowledgePassage, reference.source_id)
        policy = session.sync_session.info.get(ACCESS_POLICY_SESSION_KEY)
        if passage and isinstance(policy, GraphAccessPolicy):
            document = await session.scalar(
                knowledge_document_query(policy).where(KnowledgeDocument.id == passage.document_id)
            )
        else:
            document = (
                await session.get(KnowledgeDocument, passage.document_id) if passage else None
            )
        if passage is None or document is None:
            raise NotFoundError("claim source was not found")
        if document.turbine_id is not None and document.turbine_id != turbine_id:
            raise NotFoundError("claim source was not found within this asset")
        if any(
            getattr(document, name) not in {None, scope[name]}
            for name in ("tenant_id", "wind_farm_id")
        ):
            raise NotFoundError("claim source was not found within this asset")
        quote = reference.quote or ""
        offset = passage.text.find(quote)
        if offset < 0:
            raise InvalidTransitionError("the cited quote is not an exact passage substring")
        if hashlib.sha256(passage.text.encode()).hexdigest() != passage.text_sha256:
            raise InvalidTransitionError("passage text SHA-256 does not match its source snapshot")
        current = (
            passage.document_version == document.document_version
            and passage.source_sha256 == document.artifact_sha256
        )
        card.update(
            source={
                "artifact_uri": document.artifact_uri,
                "sha256": passage.source_sha256,
                "source_kind": "knowledge_document",
                "document_id": document.id,
                "document_version": passage.document_version,
                "passage_id": passage.id,
                "text_sha256": passage.text_sha256,
                "quote": quote,
                "quote_char_start": passage.char_start + offset,
                "quote_char_end": passage.char_start + offset + len(quote),
                "native_locator": passage.native_locator,
                "page_number": passage.page_number,
                "citation_uri": f"windops://knowledge/passages/{passage.id}",
                "integrity": "verified_at_ingestion"
                if passage.source_sha256
                else "historical_unverified",
                "content_type": document.content_type,
            },
            method={"name": "exact_quote", "parser_version": passage.parser_version},
            quality={
                "usable": current and passage.source_sha256 is not None,
                "exclusions": [] if current else ["document_version_or_hash_changed"],
            },
            applicability={
                "document_type": document.document_type,
                "document_scope": {key: getattr(document, key) for key in scope},
                "semantic_support": "requires_human_review",
            },
        )
    card["applicability"]["component_identity"] = {
        "revision": component.revision,
        "component_type": component.component_type,
        "design_reference": component.design_reference,
    }
    card["source_fingerprint"] = canonical_request_hash(card)
    return EngineeringEvidenceCard.model_validate(card).model_dump(mode="json")


async def _sources(
    session: AsyncSession, claim: EngineeringClaim
) -> tuple[list[dict[str, Any]], bool]:
    await related(session, Mission, claim.mission_id, claim.turbine_id)
    current = [
        await build_evidence_card(
            session,
            EngineeringEvidenceReference.model_validate(row["reference"]),
            turbine_id=claim.turbine_id,
            component_id=claim.component_id,
        )
        for row in claim.evidence_cards
    ]
    content = {
        name: getattr(claim, name)
        for name in (
            "mission_id",
            "component_id",
            "claim_kind",
            "conclusion",
            "applicability",
            "evidence_cards",
            "missing_evidence",
        )
    }
    content["valid_until"] = aware(claim.valid_until).isoformat()
    drift = canonical_request_hash(content) != claim.content_sha256 or any(
        old["source_fingerprint"] != new["source_fingerprint"]
        for old, new in zip(claim.evidence_cards, current, strict=True)
    )
    return current, drift


def _effective_status(claim: EngineeringClaim, current: list[dict[str, Any]], drift: bool) -> str:
    if claim.review_status in {"rejected", "withdrawn"}:
        return claim.review_status
    if aware(claim.valid_until) <= utcnow() or (
        claim.claim_kind != "retest_recommendation"
        and any(
            row["valid_until"] and aware(datetime.fromisoformat(row["valid_until"])) <= utcnow()
            for row in current
        )
    ):
        return "expired"
    if drift:
        return "source_changed"
    return claim.review_status


async def claim_detail(session: AsyncSession, claim: EngineeringClaim) -> dict[str, Any]:
    current, drift = await _sources(session, claim)
    status = _effective_status(claim, current, drift)
    reviews = await session.scalars(
        select(EngineeringClaimReview)
        .where(EngineeringClaimReview.claim_id == claim.id)
        .order_by(EngineeringClaimReview.created_at, EngineeringClaimReview.id)
    )
    return {
        **serialize(claim),
        "effective_status": status,
        "usable_for_reasoning": status == "approved",
        "permitted_use": "retest_proposal_only"
        if claim.claim_kind == "retest_recommendation"
        else "reviewed_source_interpretation",
        "reviews": [serialize(row) for row in reviews],
        "field_qualification": "unverified",
        "authorizes_work": False,
        "fixture_fallback": False,
    }


async def verify_card_sources(
    cards: list[dict[str, Any]], turbine_id: str, verifier: ArtifactVerifier, settings: Settings
) -> None:
    verified_sources: set[tuple[str, str]] = set()
    for card in cards:
        source = card["source"]
        if not source.get("artifact_uri"):
            continue
        identity = (source["artifact_uri"], source["sha256"])
        if identity in verified_sources:
            continue
        knowledge = card["reference"]["kind"] == "knowledge_passage"
        try:
            _, content_type = await verifier.read_verified_object(
                source["artifact_uri"],
                source["sha256"],
                bucket=settings.minio_knowledge_bucket
                if knowledge
                else settings.minio_field_evidence_bucket,
                prefix=f"documents/{source['document_id']}"
                if knowledge
                else artifact_prefix(turbine_id),
                allowed_content_types=ALLOWED_KNOWLEDGE_CONTENT_TYPES
                if knowledge
                else STRUCTURAL_CONTENT_TYPES,
                max_bytes=MAX_KNOWLEDGE_ARTIFACT_BYTES if knowledge else MAX_STRUCTURAL_BYTES,
            )
            if knowledge and content_type != source["content_type"]:
                raise ValueError("claim source content type changed")
            verified_sources.add(identity)
        except ValueError as exc:
            raise InvalidTransitionError(str(exc)) from exc


async def create_claim(
    session: AsyncSession, payload: EngineeringClaimCreate, subject: str
) -> dict[str, Any]:
    now = utcnow()
    if not now < payload.valid_until <= now + timedelta(days=90):
        raise InvalidTransitionError("claim expiry must be in the future and within 90 days")
    scope = await asset_scope(session, payload.turbine_id)
    await related(session, Mission, payload.mission_id, payload.turbine_id)
    cards = [
        await build_evidence_card(
            session, ref, turbine_id=payload.turbine_id, component_id=payload.component_id
        )
        for ref in payload.evidence
    ]
    if payload.claim_kind != "retest_recommendation" and any(
        card["valid_until"]
        and payload.valid_until > aware(datetime.fromisoformat(card["valid_until"]))
        for card in cards
    ):
        raise InvalidTransitionError(
            "claim validity cannot outlive a source calibration or baseline"
        )
    content = {
        **payload.model_dump(mode="json", exclude={"evidence", "turbine_id"}),
        "evidence_cards": cards,
        "valid_until": payload.valid_until.isoformat(),
    }
    digest = canonical_request_hash(content)
    claim = EngineeringClaim(
        **scope,
        **{**content, "valid_until": payload.valid_until},
        content_sha256=digest,
        created_by=subject,
    )
    session.add(claim)
    await session.flush()
    append_domain_event(
        session,
        event_type="structural.claim.created",
        aggregate_type="turbine",
        aggregate_id=claim.turbine_id,
        payload={
            "turbine_id": claim.turbine_id,
            "claim_id": claim.id,
            "mission_id": claim.mission_id,
            "revision": claim.revision,
        },
    )
    return await claim_detail(session, claim)


async def review_claim(
    session: AsyncSession,
    claim_id: str,
    request: EngineeringClaimReviewRequest,
    subject: str,
    verifier: ArtifactVerifier,
    settings: Settings,
) -> dict[str, Any]:
    claim = await session.scalar(
        select(EngineeringClaim).where(EngineeringClaim.id == claim_id).with_for_update()
    )
    if claim is None:
        raise NotFoundError("engineering claim was not found")
    if claim.revision != request.expected_revision:
        raise ConflictError("engineering claim revision changed")
    if subject == claim.created_by:
        raise InvalidTransitionError("claim authors cannot perform their own independent review")
    current, drift = await _sources(session, claim)
    if claim.review_status in {"rejected", "withdrawn"}:
        raise InvalidTransitionError("a final rejected or withdrawn claim requires a new claim")
    if request.action == "approve":
        if _effective_status(claim, current, drift) != "pending":
            raise InvalidTransitionError("expired or changed evidence requires a new claim")
        support = [card for card in current if card["reference"]["relation"] == "supports"]
        if claim.claim_kind != "retest_recommendation" and (
            claim.missing_evidence or any(not card["quality"].get("usable") for card in support)
        ):
            raise InvalidTransitionError(
                "missing or unusable supporting evidence cannot be approved"
            )
        if claim.claim_kind == "screening_finding" and not any(
            card["reference"]["kind"] in {"modal", "prestress"} for card in support
        ):
            raise InvalidTransitionError(
                "a screening finding requires actual modal or direct-force support"
            )
        await verify_card_sources(current, claim.turbine_id, verifier, settings)
    result = await session.scalar(
        update(EngineeringClaim)
        .where(
            EngineeringClaim.id == claim.id, EngineeringClaim.revision == request.expected_revision
        )
        .values(
            review_status={"approve": "approved", "reject": "rejected", "withdraw": "withdrawn"}[
                request.action
            ],
            revision=request.expected_revision + 1,
            reviewed_by=subject,
            reviewed_at=utcnow(),
            review_reason=request.reason,
        )
        .returning(EngineeringClaim.id)
        .execution_options(synchronize_session="fetch")
    )
    if result is None:
        raise ConflictError("engineering claim revision changed during review")
    session.add(
        EngineeringClaimReview(
            claim_id=claim.id,
            claim_revision=claim.revision,
            action=request.action,
            reason=request.reason,
            reviewed_by=subject,
        )
    )
    await session.flush()
    append_domain_event(
        session,
        event_type="structural.claim.reviewed",
        aggregate_type="turbine",
        aggregate_id=claim.turbine_id,
        payload={
            "turbine_id": claim.turbine_id,
            "claim_id": claim.id,
            "mission_id": claim.mission_id,
            "revision": claim.revision,
            "review_status": claim.review_status,
            "reviewed_by": subject,
        },
    )
    return await claim_detail(session, claim)
