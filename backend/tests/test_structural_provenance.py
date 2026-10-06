"""Synthetic software contracts, with actual FDD and explicit image declarations."""

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from tests.test_hybrid_structure import acquisition, identities, post

from windops_backend.config import Settings
from windops_backend.enums import Environment
from windops_backend.main import create_app
from windops_backend.model_structural import ModalObservation, StructuralAnalysisRun
from windops_backend.operations.hybrid_identity import hybrid_bundle_id
from windops_backend.operations.structural_provenance_evidence import verify_persisted_execution
from windops_backend.storage import OutboxEvent
from windops_backend.structural_contract import algorithm_identity
from windops_backend.structural_provenance import deployment_identity
from windops_backend.structural_result_identity import structural_result_hash
from windops_backend.structural_worker import process_structural_event

API_DIGEST = "sha256:" + "b" * 64
STRUCTURAL_DIGEST = "sha256:" + "c" * 64


def release_fields(release_id="synthetic-provenance-v1", *, worker=False):
    return {
        "release_id": release_id,
        "release_commit_sha": "a" * 40,
        "release_image_digest": STRUCTURAL_DIGEST if worker else API_DIGEST,
        "api_image_digest": API_DIGEST,
        "structural_image_digest": STRUCTURAL_DIGEST,
        "release_bundle_id": hybrid_bundle_id(release_id, "a" * 40, API_DIGEST, STRUCTURAL_DIGEST),
    }


def runtime_settings(**fields):
    return Settings(environment=Environment.TEST, **{"_env_file": None, **fields})


def configure_api(app, release_id="synthetic-provenance-v1"):
    # Change only the test application's trusted configuration, never request JSON.
    app.state.settings = app.state.settings.model_copy(update=release_fields(release_id))
    return app.state.settings


def test_legacy_configuration_has_no_invented_image_identity():
    assert deployment_identity(runtime_settings(), "api") is None
    assert deployment_identity(runtime_settings(), "structural-worker") is None


@pytest.mark.parametrize(
    "mutation",
    [
        {"api_image_digest": ""},
        {"structural_image_digest": ""},
        {"release_bundle_id": ""},
        {"release_bundle_id": "sha256:" + "d" * 64},
        {"release_id": "development"},
        {"release_commit_sha": "a" * 8},
        {"release_commit_sha": "0" * 40},
        {"release_image_digest": "sha256:" + "d" * 64},
        {"api_image_digest": STRUCTURAL_DIGEST},
        {"structural_image_digest": "sha256:" + "0" * 64},
        {"api_image_digest": "synthetic-tag"},
    ],
)
def test_partial_or_changed_configuration_is_rejected(mutation):
    with pytest.raises(ValidationError):
        runtime_settings(**{**release_fields(), **mutation})


@pytest.mark.parametrize(
    "field", ["api_image_digest", "structural_image_digest", "release_bundle_id"]
)
def test_a_single_hybrid_field_never_falls_back_to_legacy(field):
    with pytest.raises(ValidationError):
        runtime_settings(**{field: release_fields()[field]})


def test_two_process_roles_share_bundle_but_require_their_own_image(monkeypatch):
    api = runtime_settings(**release_fields())
    worker = runtime_settings(**release_fields(worker=True))
    assert deployment_identity(api, "api") == deployment_identity(worker, "structural-worker")
    with pytest.raises(ValueError, match="process role"):
        deployment_identity(api, "structural-worker")
    with pytest.raises(ValueError, match="process role"):
        create_app(worker)
    for key, value in release_fields().items():
        monkeypatch.setenv("WINDOPS_" + key.upper(), value)
    assert deployment_identity(runtime_settings(), "api") == deployment_identity(api, "api")


async def queued_event(app, run_id):
    async with app.state.session_factory() as session:
        event = await session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == run_id,
                OutboxEvent.event_type == "structural.analysis.requested",
            )
        )
        assert event is not None
        return event.id


async def process(app, event_id, settings=None):
    return await process_structural_event(
        app.state.session_factory,
        app.state.artifact_verifier,
        "windops-field-evidence",
        event_id,
        settings=settings,
    )


async def test_real_fdd_persists_declared_bundle_observed_versions_and_result_hash(app, client):
    configured = configure_api(app)
    declared = deployment_identity(configured, "api")
    _, sensors = await identities(client)
    record, _, _ = await acquisition(app, client, sensors)
    key = str(uuid4())
    pending = await post(client, "structural-analyses", {"record_id": record["id"]}, key)
    assert pending.status_code == 202
    run = pending.json()
    assert run["algorithm_identity"] == {**algorithm_identity(), "deployment_declared": declared}
    for replay_key in (key, str(uuid4())):
        replay = await post(client, "structural-analyses", {"record_id": record["id"]}, replay_key)
        assert replay.status_code == 202 and replay.json()["id"] == run["id"]
    injection = await post(
        client,
        "structural-analyses",
        {"record_id": record["id"], "deployment_declared": declared},
    )
    assert injection.status_code == 422
    event_id = await queued_event(app, run["id"])
    worker = runtime_settings(**release_fields(worker=True))
    assert await process(app, event_id, worker)
    detail = (await client.get(f"/api/v1/structural-analyses/{run['id']}")).json()
    assert detail["status"] == "succeeded"
    result = detail["result"]
    provenance = result["execution_provenance"]
    assert provenance["deployment_declared"] == declared
    assert provenance["runtime_image_digest_declared"] == STRUCTURAL_DIGEST
    assert provenance["image_identity_assurance"] == "deployment_declared"
    assert result["algorithm"]["deployment_declared"] == declared
    assert provenance["algorithm_observed"] == {
        **algorithm_identity(),
        "config": result["algorithm"]["config"],
    }
    package = Path(__file__).parents[1] / "src/windops_backend"
    for name, digest in provenance["execution_code_sha256"].items():
        assert digest == hashlib.sha256((package / name).read_bytes()).hexdigest()
    assert result["modes"][0]["frequency_hz"] == pytest.approx(0.5)
    expected_hash = result.pop("result_sha256")
    assert expected_hash == structural_result_hash(result)
    assert await process(app, event_id, worker) is False
    async with app.state.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(ModalObservation)) == 1
        assert await session.scalar(select(func.count()).select_from(StructuralAnalysisRun)) == 1
        persisted = await session.get(StructuralAnalysisRun, run["id"])
        assert verify_persisted_execution(persisted, configured)["result_sha256"] == expected_hash
        # A valid result hash alone cannot disguise a substituted runtime identity.
        forged = dict(persisted.result)
        forged["execution_provenance"] = {**provenance, "image_identity_assurance": "observed"}
        forged.pop("result_sha256")
        forged["result_sha256"] = structural_result_hash(forged)
        persisted.result = forged
        with pytest.raises(RuntimeError, match="execution provenance"):
            verify_persisted_execution(persisted, configured)


@pytest.mark.parametrize("mismatch", ["new_bundle", "missing_bundle", "wrong_role", "old_unbound"])
async def test_incompatible_worker_fails_before_calculation_without_observations(
    app, client, monkeypatch, mismatch
):
    if mismatch != "old_unbound":
        configure_api(app)
    _, sensors = await identities(client)
    record, _, _ = await acquisition(app, client, sensors)
    pending = await post(client, "structural-analyses", {"record_id": record["id"]})
    assert pending.status_code == 202
    run = pending.json()
    event_id = await queued_event(app, run["id"])
    settings = {
        "new_bundle": runtime_settings(**release_fields("synthetic-provenance-v2", worker=True)),
        "missing_bundle": runtime_settings(),
        "wrong_role": runtime_settings(**release_fields()),
        "old_unbound": runtime_settings(**release_fields(worker=True)),
    }[mismatch]

    async def calculation_must_not_run(*args):
        raise AssertionError("incompatible deployment must be rejected before calculation")

    monkeypatch.setattr(
        "windops_backend.structural_worker.compute_waveform", calculation_must_not_run
    )
    assert await process(app, event_id, settings)
    failed = (await client.get(f"/api/v1/structural-analyses/{run['id']}")).json()
    assert failed["status"] == "failed"
    assert failed["error_code"] == "StructuralAlgorithmVersionMismatch"
    assert failed["result"] is None
    async with app.state.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(ModalObservation)) == 0
        event = await session.get(OutboxEvent, event_id)
        assert event.status == "failed" and event.processed_at is not None
    configure_api(app, "synthetic-provenance-v2")
    new = await post(client, "structural-analyses", {"record_id": record["id"]})
    assert new.status_code == 202 and new.json()["id"] != run["id"]


async def test_legacy_actual_fdd_result_explicitly_retains_unbound_assurance(app, client):
    from tests.test_hybrid_structure import run_analysis

    _, sensors = await identities(client)
    record, _, _ = await acquisition(app, client, sensors)
    run, _ = await run_analysis(app, client, record)
    assert run["status"] == "succeeded"
    provenance = run["result"]["execution_provenance"]
    assert provenance["deployment_declared"] is None
    assert provenance["runtime_image_digest_declared"] is None
    assert provenance["image_identity_assurance"] == "unbound"
    assert "deployment_declared" not in run["algorithm_identity"]
