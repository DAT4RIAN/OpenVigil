from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr, ValidationError
from sqlalchemy import func, select

from windops_backend.benchmarks.care.anomaly import (
    ANOMALY_RUNTIME_CONTRACT_VERSION,
    ActivationGateEvidence,
    ActivationGatePolicy,
    AlarmSourceReference,
    AlertPolicyInput,
    AnomalyActivationAuthorization,
    AnomalyAlertPolicy,
    AnomalyAlertState,
    AnomalyFeatureWindow,
    AnomalyRuntimeContext,
    ArtifactReference,
    BenchmarkMetricSnapshot,
    CareAnomalyError,
    apply_alert_policy,
    build_anomaly_runtime_contract,
    build_governed_anomaly_output,
    canonical_anomaly_input_schema,
    canonical_anomaly_output_schema,
    evaluate_activation_gate,
    verify_anomaly_runtime_contract,
    verify_governed_anomaly_output,
    write_anomaly_runtime_contract,
)
from windops_backend.benchmarks.care.quality import FEATURE_SET_VERSION, QUALITY_RULE_VERSION
from windops_backend.benchmarks.care.replay import (
    CareReplayError,
    ReplaySourceRow,
    ReplayVariable,
    build_replay_sample,
    create_replay_run,
)
from windops_backend.benchmarks.care.scoring import (
    CalibrationInput,
    CareEventTruth,
    EvaluationRunSpec,
    FinalCareEvaluator,
    ModelSelectionProvenance,
    PredictionBatch,
    PredictionPoint,
    PredictionTruthVault,
    ThresholdPolicy,
    build_evaluation_artifact,
    build_prediction_artifact,
    fixed_threshold_policy,
)
from windops_backend.config import ModelInferenceTarget
from windops_backend.errors import ConflictError
from windops_backend.models import (
    Alarm,
    IngestReceipt,
    ModelDeployment,
    ModelPrediction,
    RegisteredModel,
    Turbine,
)
from windops_backend.schemas import ModelRegisterRequest
from windops_backend.services.models import activate_deployment, run_anomaly_inference
from windops_backend.storage import InMemoryArtifactVerifier

FEATURE_SET_SHA = "1" * 64
QUALITY_CONTRACT_SHA = "2" * 64
EVIDENCE_SHA = "3" * 64
MODEL_ARTIFACT_SHA = "4" * 64


def _threshold() -> ThresholdPolicy:
    return fixed_threshold_policy(
        CalibrationInput((0.1, 0.2, 0.3), "train-validation", "train-run-1"),
        value=0.5,
        version="care-threshold-v1",
    )


def _evaluation_artifact(
    model_id: str = "ANOM-CARE-001",
    model_version: str = "1.0.0",
) -> tuple[dict[str, Any], ThresholdPolicy]:
    threshold = _threshold()
    selection = ModelSelectionProvenance(
        training_run_id="train-run-1",
        feature_selection_split="train",
        early_stopping_split="train-validation",
        hyperparameter_selection_split="train-validation",
    )

    def prediction(event_id: int, score: float) -> dict[str, Any]:
        batch = PredictionBatch(
            event_id=event_id,
            farm="A",
            source_asset_id="13",
            points=tuple(
                PredictionPoint(
                    source_row_id=index,
                    source_timestamp=f"source-{index}",
                    anonymous_time=f"2022-01-01T{index // 6:02d}:{index % 6 * 10:02d}:00",
                    anomaly_score=score,
                    status_id="0",
                )
                for index in range(80)
            ),
            model_id=model_id,
            model_version=model_version,
            deployment_id=None,
            feature_set_version=FEATURE_SET_VERSION,
            feature_set_sha256=FEATURE_SET_SHA,
            quality_rule_version=QUALITY_RULE_VERSION,
            quality_contract_sha256=QUALITY_CONTRACT_SHA,
            model_selection_provenance=selection,
        )
        return build_prediction_artifact(batch, threshold, trusted_status_ids=("0",))

    predictions = [prediction(1, 1.0), prediction(2, 0.0)]
    truths = PredictionTruthVault(
        (
            CareEventTruth(1, "A", "13", "anomaly", 0, 79, "test-failure"),
            CareEventTruth(2, "A", "13", "normal", 0, 79, None),
        )
    )
    artifact = build_evaluation_artifact(
        EvaluationRunSpec(
            run_id="eval-final-1",
            purpose="final-holdout",
            generalization_protocol="within-farm-leave-one-turbine-out-v1",
            event_ids=(1, 2),
            model_id=model_id,
            model_version=model_version,
            created_at="2026-08-26T10:00:00+00:00",
            farm="A",
            held_out_asset_id="13",
        ),
        FinalCareEvaluator(truths),
        predictions,
    )
    return artifact, threshold


def _gate_policy(threshold: ThresholdPolicy) -> ActivationGatePolicy:
    return ActivationGatePolicy(
        policy_version="care-activation-v1",
        minimum_care_score=0.8,
        minimum_event_detection_rate=1.0,
        maximum_normal_event_false_positive_rate=0.0,
        required_farms=("A",),
        required_generalization_protocols=("within-farm-leave-one-turbine-out-v1",),
        required_feature_set_version=FEATURE_SET_VERSION,
        required_feature_set_sha256=FEATURE_SET_SHA,
        required_quality_rule_version=QUALITY_RULE_VERSION,
        required_quality_contract_sha256=QUALITY_CONTRACT_SHA,
        required_threshold_policy_version=threshold.version,
        required_threshold_policy_sha256=str(threshold.to_dict()["threshold_policy_sha256"]),
    )


def _gate_evidence(
    artifact: dict[str, Any],
    *,
    deployment_id: str = "deployment-1",
    model_artifact_sha256: str = MODEL_ARTIFACT_SHA,
) -> ActivationGateEvidence:
    return ActivationGateEvidence(
        evaluation_run_id="eval-final-1",
        evaluation_status="completed",
        invalidated=False,
        evaluation_artifact=artifact,
        metric_snapshot=BenchmarkMetricSnapshot.from_evaluation_artifact(artifact),
        model_id=str(artifact["run"]["model_id"]),
        model_version=str(artifact["run"]["model_version"]),
        model_artifact_sha256=model_artifact_sha256,
        deployment_id=deployment_id,
        deployment_version=deployment_id,
        approval_ids=("approval-1",),
        audit_event_ids=("audit-1",),
    )


def _replay_samples(
    run_id: str = "pred0001",
    *,
    value_offset: float = 0,
) -> tuple[Any, list[dict[str, Any]]]:
    variable = ReplayVariable("generator_bearing_temperature_avg", "°C")
    now = datetime.now(UTC).replace(microsecond=0)
    run = create_replay_run(
        benchmark_replay_run_id=run_id,
        farm="A",
        event_id=7,
        source_asset_id="13",
        replay_anchor_at=now - timedelta(minutes=20),
        selected_variables=(variable,),
        window_start_row_id=10,
        window_end_row_id=12,
        created_by="anomaly-test",
        created_at=now,
    )
    samples = [
        build_replay_sample(
            run,
            ReplaySourceRow(
                row_id,
                f"source-{row_id}",
                f"2022-01-01T00:{row_id:02d}:00",
                "0",
                ((variable.canonical_variable, float(row_id) + value_offset),),
                600,
            ),
            variable,
            quality_rule_id=QUALITY_RULE_VERSION,
        )
        for row_id in range(10, 13)
    ]
    return run, samples


def _model_request(kind: str = "anomaly") -> dict[str, Any]:
    return {
        "model_id": "ANOM-CARE-001",
        "name": "CARE anomaly model",
        "version": "1.0.0",
        "kind": kind,
        "artifact_uri": "minio://windops-model-artifacts/models/ANOM-CARE-001/package.onnx",
        "artifact_sha256": MODEL_ARTIFACT_SHA,
        "content_type": "application/onnx",
        "input_schema": canonical_anomaly_input_schema(),
        "output_schema": canonical_anomaly_output_schema(),
    }


def _alert_input(
    policy: AnomalyAlertPolicy,
    prediction_id: str,
    sequence: int,
    observed_at: datetime,
    score: float,
    *,
    start_sequence: int | None = None,
    quality: Literal["good", "uncertain", "bad"] = "good",
) -> AlertPolicyInput:
    return AlertPolicyInput(
        prediction_id=prediction_id,
        model_id=policy.model_id,
        model_version=policy.model_version,
        deployment_id=policy.deployment_id,
        deployment_version=policy.deployment_version,
        component=policy.component,
        asset_scope=policy.asset_scope,
        start_sequence=sequence if start_sequence is None else start_sequence,
        end_sequence=sequence,
        observed_at=observed_at,
        anomaly_score=score,
        binary_prediction=score > policy.trigger_threshold,
        quality=quality,
    )


def test_anomaly_registration_contract_is_conditional_and_forbids_fake_rul() -> None:
    request = ModelRegisterRequest.model_validate(_model_request())
    assert request.kind == "anomaly"

    missing = _model_request()
    missing["output_schema"] = json.loads(json.dumps(missing["output_schema"]))
    missing["output_schema"]["required"].remove("binary_prediction")
    with pytest.raises(ValidationError, match="binary_prediction"):
        ModelRegisterRequest.model_validate(missing)

    fake_rul = _model_request()
    fake_rul["output_schema"] = json.loads(json.dumps(fake_rul["output_schema"]))
    fake_rul["output_schema"]["required"].append("remaining_useful_life_days")
    fake_rul["output_schema"]["properties"]["remaining_useful_life_days"] = {"type": "number"}
    with pytest.raises(ValidationError, match="must not fabricate"):
        ModelRegisterRequest.model_validate(fake_rul)


def test_governed_anomaly_output_has_provenance_and_no_truth_or_predictive_placeholders() -> None:
    run, samples = _replay_samples()
    window = AnomalyFeatureWindow.from_replay_samples(
        samples,
        feature_set_version=FEATURE_SET_VERSION,
        quality_rule_version=QUALITY_RULE_VERSION,
    )
    output = build_governed_anomaly_output(
        {"anomaly_score": 0.9, "binary_prediction": True, "component": "unknown"},
        window,
        AnomalyRuntimeContext(
            "ANOM-CARE-001",
            "1.0.0",
            "deployment-1",
            "deployment-1",
            _threshold(),
            ArtifactReference("minio://care/predictions/window.json", EVIDENCE_SHA),
        ),
    )
    verify_governed_anomaly_output(output)
    assert output["benchmark_replay_run_id"] == run.benchmark_replay_run_id
    assert output["feature_start_sequence"] == 10
    assert output["feature_end_sequence"] == 12
    assert output["prediction_truth_present"] is False
    assert not set(output).intersection({"failure_probability_30d", "remaining_useful_life_days"})
    policy_input = AlertPolicyInput.from_governed_output("prediction-1", output, quality="good")
    assert policy_input.asset_scope == run.online_turbine_id

    tampered = dict(output)
    tampered["binary_prediction"] = False
    unsigned = {key: value for key, value in tampered.items() if key != "anomaly_prediction_sha256"}
    tampered["anomaly_prediction_sha256"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with pytest.raises(CareAnomalyError, match="strict threshold"):
        verify_governed_anomaly_output(tampered)
    with pytest.raises(CareAnomalyError, match="forge provenance"):
        build_governed_anomaly_output(
            {
                "anomaly_score": 0.9,
                "binary_prediction": True,
                "component": "unknown",
                "model_id": "forged",
            },
            window,
            AnomalyRuntimeContext(
                "ANOM-CARE-001",
                "1.0.0",
                "deployment-1",
                "deployment-1",
                _threshold(),
                ArtifactReference("minio://care/predictions/window.json", EVIDENCE_SHA),
            ),
        )


def test_anomaly_feature_window_cannot_cross_replay_runs() -> None:
    _first_run, first = _replay_samples("pred0001")
    _second_run, second = _replay_samples("pred0002")
    with pytest.raises(CareReplayError, match="cannot cross"):
        AnomalyFeatureWindow.from_replay_samples(
            [first[0], second[0]],
            feature_set_version=FEATURE_SET_VERSION,
            quality_rule_version=QUALITY_RULE_VERSION,
        )


def test_alert_policy_persists_trigger_recovery_cooldown_and_idempotency() -> None:
    policy = AnomalyAlertPolicy(
        policy_id="care-alert-policy",
        policy_version="1",
        model_id="ANOM-CARE-001",
        model_version="1.0.0",
        deployment_id="deployment-1",
        deployment_version="deployment-1",
        component="unknown",
        asset_scope="CR6-PRED0001-A13-E7",
        trigger_threshold=0.5,
        consecutive_trigger_windows=2,
        recovery_threshold=0.3,
        consecutive_recovery_windows=2,
        cooldown_seconds=60,
    )
    assert AnomalyAlertPolicy.from_document(policy.to_document()) == policy
    state = AnomalyAlertState.initial(policy)
    now = datetime(2026, 8, 26, 10, 0, tzinfo=UTC)

    first = apply_alert_policy(
        policy,
        state,
        prediction=_alert_input(policy, "prediction-1", 1, now, 0.8),
    )
    assert first.action == "none" and first.state.consecutive_trigger_count == 1
    triggered = apply_alert_policy(
        policy,
        first.state,
        prediction=_alert_input(policy, "prediction-2", 2, now + timedelta(seconds=10), 0.9),
        alarm_id_factory="alarm-1",
    )
    assert triggered.action == "trigger" and triggered.state.active_alarm_id == "alarm-1"
    duplicate = apply_alert_policy(
        policy,
        triggered.state,
        prediction=_alert_input(policy, "prediction-2", 2, now + timedelta(seconds=10), 0.9),
    )
    assert duplicate.action == "duplicate" and duplicate.state == triggered.state

    recovering = apply_alert_policy(
        policy,
        triggered.state,
        prediction=_alert_input(policy, "prediction-3", 3, now + timedelta(seconds=20), 0.2),
    )
    recovered = apply_alert_policy(
        policy,
        recovering.state,
        prediction=_alert_input(policy, "prediction-4", 4, now + timedelta(seconds=30), 0.2),
    )
    assert recovered.action == "recover" and recovered.state.active_alarm_id is None
    restored = AnomalyAlertState.from_document(recovered.state.to_document())
    assert restored == recovered.state

    count_one = apply_alert_policy(
        policy,
        restored,
        prediction=_alert_input(policy, "prediction-5", 5, now + timedelta(seconds=35), 0.8),
    )
    cooldown = apply_alert_policy(
        policy,
        count_one.state,
        prediction=_alert_input(policy, "prediction-6", 6, now + timedelta(seconds=40), 0.8),
    )
    assert cooldown.action == "none" and cooldown.state.status == "cooldown"
    retriggered = apply_alert_policy(
        policy,
        cooldown.state,
        prediction=_alert_input(policy, "prediction-7", 7, now + timedelta(seconds=80), 0.8),
        alarm_id_factory="alarm-2",
    )
    assert retriggered.action == "trigger"
    with pytest.raises(CareAnomalyError, match="out-of-order"):
        apply_alert_policy(
            policy,
            retriggered.state,
            prediction=_alert_input(policy, "prediction-old", 6, now + timedelta(seconds=90), 0.8),
        )
    wrong_identity = replace(
        _alert_input(policy, "prediction-wrong-model", 8, now + timedelta(seconds=100), 0.8),
        model_id="another-model",
    )
    with pytest.raises(CareAnomalyError, match="does not match"):
        apply_alert_policy(policy, retriggered.state, prediction=wrong_identity)


def test_alert_policy_handles_missing_uncertain_disabled_and_alarm_sources() -> None:
    policy = AnomalyAlertPolicy(
        "policy-1",
        "1",
        "model-1",
        "1",
        "deployment-1",
        "deployment-1",
        "unknown",
        "asset-1",
        0.5,
        2,
        0.2,
        1,
        0,
        missing_window_behavior="reset",
        uncertain_quality_behavior="hold",
    )
    now = datetime(2026, 8, 26, 10, 0, tzinfo=UTC)
    state = apply_alert_policy(
        policy,
        AnomalyAlertState.initial(policy),
        prediction=_alert_input(policy, "p1", 1, now, 0.8),
    ).state
    uncertain = apply_alert_policy(
        policy,
        state,
        prediction=_alert_input(policy, "p2", 2, now, 0.8, quality="uncertain"),
    )
    assert uncertain.state.consecutive_trigger_count == 1
    missing = apply_alert_policy(
        policy,
        uncertain.state,
        prediction=_alert_input(policy, "p3", 5, now, 0.0),
    )
    assert missing.state.consecutive_trigger_count == 0
    disabled = apply_alert_policy(
        replace(policy, enabled=False),
        missing.state,
        prediction=_alert_input(policy, "p4", 6, now, 0.8),
    )
    assert disabled.action == "disabled"

    assert (
        AlarmSourceReference(model_prediction_id="prediction-1").requires_synthetic_ingest_receipt
        is False
    )
    assert AlarmSourceReference(source_event_id="source-1", model_prediction_id="prediction-1")
    with pytest.raises(CareAnomalyError, match="must reference"):
        AlarmSourceReference()


def test_server_activation_gate_recomputes_metrics_and_rejects_forged_state() -> None:
    artifact, threshold = _evaluation_artifact()
    policy = _gate_policy(threshold)
    evidence = _gate_evidence(artifact)
    authorization = evaluate_activation_gate(
        policy,
        evidence,
        authorized_at=datetime(2026, 8, 26, 10, 0, tzinfo=UTC),
    )
    assert authorization.metric_snapshot_sha256 == evidence.metric_snapshot.snapshot_sha256

    with pytest.raises(CareAnomalyError, match="within 0..1"):
        replace(policy, minimum_care_score=1.01)
    with pytest.raises(CareAnomalyError, match="completed and not invalidated"):
        evaluate_activation_gate(
            policy,
            replace(evidence, invalidated=True),
            authorized_at=datetime(2026, 8, 26, 10, 0, tzinfo=UTC),
        )
    forged_snapshot = replace(
        evidence.metric_snapshot,
        care_score=0.0,
        snapshot_sha256="",
    )
    with pytest.raises(CareAnomalyError, match="does not match"):
        evaluate_activation_gate(
            policy,
            replace(evidence, metric_snapshot=forged_snapshot),
            authorized_at=datetime(2026, 8, 26, 10, 0, tzinfo=UTC),
        )
    with pytest.raises(CareAnomalyError, match="version matrix"):
        evaluate_activation_gate(
            replace(policy, required_feature_set_sha256="9" * 64),
            evidence,
            authorized_at=datetime(2026, 8, 26, 10, 0, tzinfo=UTC),
        )
    with pytest.raises(CareAnomalyError, match="not issued"):
        AnomalyActivationAuthorization(
            "ANOM-CARE-001",
            "1.0.0",
            MODEL_ARTIFACT_SHA,
            "deployment-1",
            "deployment-1",
            "eval-final-1",
            evidence.metric_snapshot.snapshot_sha256,
            policy.policy_version,
            datetime(2026, 8, 26, 10, 0, tzinfo=UTC),
            object(),
        )


def test_anomaly_runtime_contract_is_stable(tmp_path: Path) -> None:
    contract = build_anomaly_runtime_contract()
    assert contract["schema_version"] == ANOMALY_RUNTIME_CONTRACT_VERSION
    verify_anomaly_runtime_contract(contract)
    first = tmp_path / "anomaly-contract.json"
    second = tmp_path / "anomaly-contract-repeat.json"
    write_anomaly_runtime_contract(first)
    write_anomaly_runtime_contract(second)
    assert first.read_bytes() == second.read_bytes()


class _FakeAnomalyClient:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, Any], str]] = []

    async def predict(
        self,
        target: ModelInferenceTarget,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> tuple[dict[str, Any], int]:
        del target
        self.calls.append((payload, idempotency_key))
        return {
            "anomaly_score": 0.9,
            "binary_prediction": True,
            "component": "unknown",
        }, 19


def _manager_headers(key: str) -> dict[str, str]:
    return {
        "X-WindOps-Test-Principal": "care-model-operator@example.com",
        "X-WindOps-Test-Role": "operations_manager",
        "Idempotency-Key": key,
    }


@pytest.mark.asyncio
async def test_anomaly_register_stage_server_gate_infer_and_retry_without_fake_receipt(
    app: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    package = b"verified CARE anomaly package"
    package_sha = hashlib.sha256(package).hexdigest()
    payload = _model_request()
    payload["artifact_sha256"] = package_sha
    uri = str(payload["artifact_uri"])
    verifier = app.state.artifact_verifier
    assert isinstance(verifier, InMemoryArtifactVerifier)
    verifier.register_object(uri, package, "application/onnx")
    app.state.settings.model_inference_targets["anomaly-primary"] = ModelInferenceTarget(
        endpoint_url="http://anomaly.test/v1/predict",
        api_token=SecretStr("test-anomaly-token"),
    )

    registered = await client.post(
        "/api/v1/models",
        headers=_manager_headers("care-anomaly-register-1"),
        json=payload,
    )
    assert registered.status_code == 201, registered.text
    staged = await client.post(
        "/api/v1/models/ANOM-CARE-001/deployments",
        headers=_manager_headers("care-anomaly-stage-1"),
        json={
            "target_id": "anomaly-primary",
            "stage": "production",
            "evaluation_gate": {"frontend_claim": "passed"},
        },
    )
    assert staged.status_code == 201, staged.text
    deployment_id = str(staged.json()["deployment_id"])
    bypass = await client.post(
        f"/api/v1/models/deployments/{deployment_id}/activate",
        headers=_manager_headers("care-anomaly-bypass-1"),
        json={"traffic_percent": 100, "reason": "frontend claims metrics passed"},
    )
    assert bypass.status_code != 200

    artifact, threshold = _evaluation_artifact()
    authorization = evaluate_activation_gate(
        _gate_policy(threshold),
        _gate_evidence(
            artifact,
            deployment_id=deployment_id,
            model_artifact_sha256=package_sha,
        ),
        authorized_at=datetime.now(UTC),
    )
    run, samples = _replay_samples()
    async with app.state.session_factory() as session, session.begin():
        session.add(
            Turbine(
                id=run.online_turbine_id,
                wind_farm_id="WF-EAST-01",
                model="CARE v6 isolated replay",
                status="running",
                health_score=100,
            )
        )
        active = await activate_deployment(
            session,
            deployment_id=deployment_id,
            traffic_percent=100,
            reason="server-verified CARE benchmark gate",
            subject="care-model-operator@example.com",
            anomaly_authorization=authorization,
        )
        assert active.status == "active"

    fake = _FakeAnomalyClient()
    evidence_ref = ArtifactReference("minio://care/predictions/window.json", EVIDENCE_SHA)
    async with app.state.session_factory() as session, session.begin():
        prediction = await run_anomaly_inference(
            session,
            app.state.settings,
            fake,
            deployment_id=deployment_id,
            feature_samples=samples,
            feature_set_version=FEATURE_SET_VERSION,
            quality_rule_version=QUALITY_RULE_VERSION,
            threshold_policy=threshold,
            evidence_artifact=evidence_ref,
            subject="care-worker",
        )
        prediction_id = prediction.id
        assert prediction.status == "succeeded"
        assert prediction.output["binary_prediction"] is True
        assert "remaining_useful_life_days" not in prediction.output

    async with app.state.session_factory() as session, session.begin():
        replayed = await run_anomaly_inference(
            session,
            app.state.settings,
            fake,
            deployment_id=deployment_id,
            feature_samples=samples,
            feature_set_version=FEATURE_SET_VERSION,
            quality_rule_version=QUALITY_RULE_VERSION,
            threshold_policy=threshold,
            evidence_artifact=evidence_ref,
            subject="care-worker",
        )
        assert replayed.id == prediction_id
    assert len(fake.calls) == 1

    changed_samples = json.loads(json.dumps(samples))
    changed_samples[0]["value"] += 1
    async with app.state.session_factory() as session:
        with pytest.raises(ConflictError, match="different governed feature window"):
            await run_anomaly_inference(
                session,
                app.state.settings,
                fake,
                deployment_id=deployment_id,
                feature_samples=changed_samples,
                feature_set_version=FEATURE_SET_VERSION,
                quality_rule_version=QUALITY_RULE_VERSION,
                threshold_policy=threshold,
                evidence_artifact=evidence_ref,
                subject="care-worker",
            )

    async with app.state.session_factory() as session:
        assert int(await session.scalar(select(func.count(ModelPrediction.id))) or 0) == 1
        assert (
            int(await session.scalar(select(func.count(IngestReceipt.source_event_id))) or 0) == 0
        )
        assert int(await session.scalar(select(func.count(Alarm.id))) or 0) == 0
        model = await session.get(RegisteredModel, "ANOM-CARE-001")
        deployment = await session.get(ModelDeployment, deployment_id)
        assert model is not None and model.kind == "anomaly"
        assert deployment is not None and deployment.status == "active"
