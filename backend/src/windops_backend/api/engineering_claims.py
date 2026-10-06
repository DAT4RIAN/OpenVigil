from typing import Any

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.ext.asyncio import AsyncSession

from windops_backend.api.deps import (
    Principal,
    get_artifact_verifier,
    get_runtime_settings,
    get_session,
    require_read_access,
    require_roles,
)
from windops_backend.api.structural import _command
from windops_backend.config import Settings
from windops_backend.errors import NotFoundError
from windops_backend.model_engineering_claim import EngineeringClaim
from windops_backend.models import Mission, TowerComponent
from windops_backend.schema_engineering_claim import (
    EngineeringClaimCreate,
    EngineeringClaimReviewRequest,
)
from windops_backend.services.engineering_claims import claim_detail, create_claim, review_claim
from windops_backend.services.structural import asset_scope, related
from windops_backend.storage import ArtifactVerifier

router = APIRouter(tags=["engineering-claims"])


@router.post("/engineering-claims", status_code=201)
async def add_engineering_claim(
    payload: EngineeringClaimCreate,
    response: Response,
    key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_roles("operations_manager", "maintenance_reviewer")),
) -> dict[str, Any]:
    await asset_scope(session, payload.turbine_id)
    await related(session, Mission, payload.mission_id, payload.turbine_id)
    await related(session, TowerComponent, payload.component_id, payload.turbine_id)
    # Recheck all source grants on receipt replay as well as on first creation.
    from windops_backend.services.engineering_claims import build_evidence_card

    for reference in payload.evidence:
        await build_evidence_card(
            session, reference, turbine_id=payload.turbine_id, component_id=payload.component_id
        )
    return await _command(
        session,
        response,
        principal,
        key,
        "claim.create",
        payload.mission_id,
        payload,
        lambda: create_claim(session, payload, principal.subject),
    )


@router.get("/engineering-claims/{claim_id}")
async def engineering_claim_detail(
    claim_id: str,
    session: AsyncSession = Depends(get_session),
    _principal: Principal = Depends(require_read_access),
) -> dict[str, Any]:
    claim = await session.get(EngineeringClaim, claim_id)
    if claim is None:
        raise NotFoundError("engineering claim was not found")
    return await claim_detail(session, claim)


@router.post("/engineering-claims/{claim_id}/review")
async def review_engineering_claim(
    claim_id: str,
    payload: EngineeringClaimReviewRequest,
    response: Response,
    key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_roles("operations_manager", "maintenance_reviewer")),
    verifier: ArtifactVerifier = Depends(get_artifact_verifier),
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    claim = await session.get(EngineeringClaim, claim_id)
    if claim is None:
        raise NotFoundError("engineering claim was not found")
    await claim_detail(session, claim)
    return await _command(
        session,
        response,
        principal,
        key,
        "claim.review",
        claim_id,
        payload,
        lambda: review_claim(session, claim_id, payload, principal.subject, verifier, settings),
        status_code=200,
    )
