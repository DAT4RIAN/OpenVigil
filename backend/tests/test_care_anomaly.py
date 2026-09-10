from __future__ import annotations

import base64
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
from windops_backend.benchmarks.care.online_contract import (
    ONLINE_ALERT_POLICY_ID,
    ONLINE_ALERT_POLICY_VERSION,
    ONLINE_COMPONENT,
    ONLINE_RUNTIME_SCHEMA_VERSION,
    ONLINE_SCORE_TRANSFORM_VERSION,
    ONLINE_THRESHOLD_POLICY_VERSION,
    canonical_online_hash,
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
from windops_backend.benchmarks.care.trust import (
    APPROVAL_LINEAGE_SCHEMA_VERSION,
    load_official_care_trust_anchor,
    verify_care_trust_anchor,
)
from windops_backend.config import ModelInferenceTarget
from windops_backend.errors import ConflictError
from windops_backend.models import (
    Alarm,
    BenchmarkDatasetVersion,
    BenchmarkEvaluationRun,
    DomainEvent,
    IngestReceipt,
    ModelDeployment,
    ModelPrediction,
    RegisteredModel,
    Turbine,
)
from windops_backend.models import (
    BenchmarkMetricSnapshot as PersistedMetricSnapshot,
)
from windops_backend.schemas import ModelRegisterRequest
from windops_backend.services.models import run_anomaly_inference
from windops_backend.storage import InMemoryArtifactVerifier

FEATURE_SET_SHA = "1" * 64
QUALITY_CONTRACT_SHA = "2" * 64
EVIDENCE_SHA = "3" * 64
MODEL_ARTIFACT_SHA = "4" * 64
MODEL_PACKAGE_SHA = "5" * 64


def _approved_lineage() -> dict[str, Any]:
    anchor = load_official_care_trust_anchor()
    root = verify_care_trust_anchor(anchor)
    source = root["source"]
    quality = root["quality"]
    approval = root["approval"]
    signature = base64.b64decode(str(root["signature_base64"]))
    return {
        "schema_version": APPROVAL_LINEAGE_SCHEMA_VERSION,
        "root_id": root["root_id"],
        "approved_root_sha256": root["approved_root_sha256"],
        "signature_algorithm": approval["algorithm"],
        "signature_key_id": approval["key_id"],
        "signature_sha256": hashlib.sha256(signature).hexdigest(),
        "canonical_source_contract_sha256": source["canonical_source_contract_sha256"],
        "canonical_quality_policy_sha256": quality["canonical_quality_policy_sha256"],
        "source_manifest_sha256": "6" * 64,
        "quality_contract_sha256": "7" * 64,
        "source_archive_sha256": source["archive"]["sha256"],
    }


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
        approval_lineage=_approved_lineage(),
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
        "metrics": {
            "model_package_sha256": MODEL_PACKAGE_SHA,
            "care_approval": _approved_lineage(),
        },
    }


def _online_runtime(
    *,
    model_artifact_uri: str,
    evaluation_run_id: str,
    threshold: ThresholdPolicy,
) -> dict[str, Any]:
    online_threshold_payload = {
        "value": 0.5,
        "version": ONLINE_THRESHOLD_POLICY_VERSION,
        "prediction_truth_used": False,
    }
    online_threshold = {
        **online_threshold_payload,
        "threshold_policy_sha256": canonical_online_hash(online_threshold_payload),
    }
    payload: dict[str, Any] = {
        "schema_version": ONLINE_RUNTIME_SCHEMA_VERSION,
        "model_id": "ANOM-CARE-001",
        "model_version": "1.0.0",
        "model_package_sha256": MODEL_PACKAGE_SHA,
        "evaluation_run_id": evaluation_run_id,
        "feature_set_version": FEATURE_SET_VERSION,
        "quality_rule_version": QUALITY_RULE_VERSION,
        "score_transform_version": ONLINE_SCORE_TRANSFORM_VERSION,
        "offline_threshold_policy_sha256": threshold.to_dict()["threshold_policy_sha256"],
        "online_threshold_policy": online_threshold,
        "evidence_artifact": {
            "uri": model_artifact_uri,
            "sha256": MODEL_PACKAGE_SHA,
        },
        "alert_policy_template": {
            "policy_id": ONLINE_ALERT_POLICY_ID,
            "policy_version": ONLINE_ALERT_POLICY_VERSION,
            "component": ONLINE_COMPONENT,
            "trigger_threshold": 0.5,
            "consecutive_trigger_windows": 3,
            "consecutive_recovery_windows": 2,
            "prediction_truth_used": False,
        },
        "release_claim": "development-vertical-slice-only",
        "prediction_truth_used": False,
    }
    return {**payload, "runtime_configuration_sha256": canonical_online_hash(payload)}


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


async def _persist_authoritative_activation_evidence(
    app: FastAPI,
    artifact: dict[str, Any],
    threshold: ThresholdPolicy,
    *,
    model_artifact_uri: str,
    model_artifact_sha256: str,
) -> tuple[str, str]:
    evaluation_uri = "minio://windops-care-benchmarks/care/v6/reports/evaluations/eval-final-1.json"
    body = (json.dumps(artifact, ensure_ascii=False, sort_keys=True) + "\n").encode()
    verifier = app.state.artifact_verifier
    assert isinstance(verifier, InMemoryArtifactVerifier)
    evaluation_sha256 = verifier.register_object(evaluation_uri, body, "application/json")
    snapshot = BenchmarkMetricSnapshot.from_evaluation_artifact(artifact)
    metrics = (
        ("care_score", snapshot.care_score, 0.8, "gte"),
        ("event_detection_rate", snapshot.event_detection_rate, 1.0, "gte"),
        (
            "normal_event_false_positive_rate",
            snapshot.normal_event_false_positive_rate,
            0.0,
            "lte",
        ),
        ("unscorable_event_count", float(snapshot.unscorable_event_count), 0.0, "eq"),
        ("data_failure_event_count", float(snapshot.data_failure_event_count), 0.0, "eq"),
        ("model_failure_event_count", float(snapshot.model_failure_event_count), 0.0, "eq"),
    )
    async with app.state.session_factory() as session, session.begin():
        if await session.get(BenchmarkDatasetVersion, "care-v6") is None:
            session.add(
                BenchmarkDatasetVersion(
                    id="care-v6",
                    tenant_id="tenant-east-china",
                    dataset_id="care-v6",
                    version="v6",
                    status="ready",
                    source_uri="minio://windops-care-benchmarks/care/v6/raw/source.zip",
                    manifest_uri="minio://windops-care-benchmarks/care/v6/reports/source.json",
                    manifest_sha256="8" * 64,
                    content_sha256="9" * 64,
                    source_archive_md5="a" * 32,
                    source_archive_sha256="b" * 64,
                    size_bytes=1,
                    file_count=1,
                    license_name="CC BY-SA 4.0",
                    license_url="https://creativecommons.org/licenses/by-sa/4.0/",
                    doi="10.5281/zenodo.15846963",
                    citation="CARE v6 test fixture",
                    attribution={},
                    created_by="care-test",
                )
            )
            await session.flush()
        session.add(
            BenchmarkEvaluationRun(
                id="eval-final-1",
                dataset_version_id="care-v6",
                model_id="ANOM-CARE-001",
                model_version="1.0.0",
                run_kind="final-holdout",
                protocol_version="within-farm-leave-one-turbine-out-v1",
                farm="A",
                status="completed",
                feature_set_version=FEATURE_SET_VERSION,
                quality_rule_version=QUALITY_RULE_VERSION,
                threshold_policy_version=threshold.version,
                threshold_policy_sha256=str(threshold.to_dict()["threshold_policy_sha256"]),
                random_seed=0,
                input_identity_sha256="c" * 64,
                artifact_uri=evaluation_uri,
                artifact_sha256=evaluation_sha256,
                requested_event_count=snapshot.requested_event_count,
                scored_event_count=snapshot.scored_event_count,
                failed_event_count=(
                    snapshot.data_failure_event_count + snapshot.model_failure_event_count
                ),
                unscorable_event_count=snapshot.unscorable_event_count,
                extension_data={
                    "model_package": {
                        "artifact_uri": model_artifact_uri,
                        "file_sha256": model_artifact_sha256,
                        "document_sha256": MODEL_PACKAGE_SHA,
                    },
                    "care_approval": _approved_lineage(),
                },
                created_by="care-test",
                completed_at=datetime.now(UTC),
            )
        )
        for index, (name, value, threshold_value, direction) in enumerate(metrics):
            passed = (
                value >= threshold_value
                if direction == "gte"
                else value <= threshold_value
                if direction == "lte"
                else value == threshold_value
            )
            session.add(
                PersistedMetricSnapshot(
                    id=f"eval-final-1-m-{index}",
                    evaluation_run_id="eval-final-1",
                    metric_name=name,
                    protocol_version="care-score-v6",
                    metric_version="care-activation-test-v1",
                    value=value,
                    unit="ratio" if "rate" in name or name == "care_score" else "events",
                    is_release_metric=True,
                    threshold_value=threshold_value,
                    threshold_direction=direction,
                    passed=passed,
                    details={"evaluation_artifact_sha256": evaluation_sha256},
                )
            )
    return evaluation_uri, evaluation_sha256


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
    artifact, threshold = _evaluation_artifact()
    runtime = _online_runtime(
        model_artifact_uri=uri,
        evaluation_run_id="eval-final-1",
        threshold=threshold,
    )
    staged = await client.post(
        "/api/v1/models/ANOM-CARE-001/deployments",
        headers=_manager_headers("care-anomaly-stage-1"),
        json={
            "target_id": "anomaly-primary",
            "stage": "production",
            "evaluation_gate": {"care_online_runtime": runtime},
        },
    )
    assert staged.status_code == 201, staged.text
    deployment_id = str(staged.json()["deployment_id"])
    bypass = await client.post(
        f"/api/v1/models/deployments/{deployment_id}/activate",
        headers=_manager_headers("care-anomaly-bypass-1"),
        json={"traffic_percent": 100, "reason": "frontend claims metrics passed"},
    )
    assert bypass.status_code == 422
    assert bypass.json()["error"]["code"] == "ANOMALY_ACTIVATION_BINDING_INVALID"

    await _persist_authoritative_activation_evidence(
        app,
        artifact,
        threshold,
        model_artifact_uri=uri,
        model_artifact_sha256=package_sha,
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

    activated = await client.post(
        f"/api/v1/models/deployments/{deployment_id}/activate",
        headers=_manager_headers("care-anomaly-http-activate-1"),
        json={
            "traffic_percent": 100,
            "reason": "server-verified CARE benchmark gate",
        },
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "active"
    assert (
        activated.json()["evaluation_gate"]["server_authorization"]["consumed_in_transaction"]
        is True
    )
    assert (
        activated.json()["evaluation_gate"]["server_authorization"]["care_approved_root_sha256"]
        == _approved_lineage()["approved_root_sha256"]
    )
    concurrent = await client.post(
        f"/api/v1/models/deployments/{deployment_id}/activate",
        headers=_manager_headers("care-anomaly-http-concurrent-1"),
        json={
            "traffic_percent": 100,
            "reason": "concurrent activation must not rewrite routing",
        },
    )
    assert concurrent.status_code == 409
    assert concurrent.json()["error"]["code"] == "ANOMALY_ACTIVATION_CONCURRENT_CHANGE"

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

    replacement = await client.post(
        "/api/v1/models/ANOM-CARE-001/deployments",
        headers=_manager_headers("care-anomaly-stage-replacement-1"),
        json={
            "target_id": "anomaly-primary",
            "stage": "production",
            "evaluation_gate": {"care_online_runtime": runtime},
        },
    )
    assert replacement.status_code == 201, replacement.text
    replacement_id = str(replacement.json()["deployment_id"])
    replacement_activation = await client.post(
        f"/api/v1/models/deployments/{replacement_id}/activate",
        headers=_manager_headers("care-anomaly-activate-replacement-1"),
        json={"traffic_percent": 100, "reason": "activate governed replacement"},
    )
    assert replacement_activation.status_code == 200, replacement_activation.text
    rolled_back = await client.post(
        "/api/v1/models/ANOM-CARE-001/rollback",
        headers=_manager_headers("care-anomaly-http-rollback-1"),
        json={
            "target_deployment_id": deployment_id,
            "reason": "rollback to the previous governed deployment",
        },
    )
    assert rolled_back.status_code == 200, rolled_back.text
    assert rolled_back.json()["deployment_id"] == deployment_id
    assert rolled_back.json()["rollback_from_id"] == replacement_id
    async with app.state.session_factory() as session:
        active_rows = list(
            (
                await session.scalars(
                    select(ModelDeployment).where(
                        ModelDeployment.stage == "production",
                        ModelDeployment.status == "active",
                    )
                )
            ).all()
        )
        assert [(row.id, row.traffic_percent) for row in active_rows] == [(deployment_id, 100)]
        event_types = list(
            (
                await session.scalars(
                    select(DomainEvent.event_type)
                    .where(DomainEvent.aggregate_id == deployment_id)
                    .order_by(DomainEvent.sequence)
                )
            ).all()
        )
        assert "model.activation.authorization-consumed" in event_types
        assert "model.activation.denied" in event_types
        assert "model.deployment.rolled-back" in event_types


@pytest.mark.asyncio
async def test_anomaly_http_activation_failures_are_stable_audited_and_atomic(
    app: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    package = b"second verified CARE anomaly package"
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
        headers=_manager_headers("care-anomaly-negative-register-1"),
        json=payload,
    )
    assert registered.status_code == 201, registered.text
    artifact, threshold = _evaluation_artifact()
    runtime = _online_runtime(
        model_artifact_uri=uri,
        evaluation_run_id="eval-final-1",
        threshold=threshold,
    )
    staged = await client.post(
        "/api/v1/models/ANOM-CARE-001/deployments",
        headers=_manager_headers("care-anomaly-negative-stage-1"),
        json={
            "target_id": "anomaly-primary",
            "stage": "production",
            "evaluation_gate": {"care_online_runtime": runtime},
        },
    )
    assert staged.status_code == 201, staged.text
    deployment_id = str(staged.json()["deployment_id"])
    evaluation_uri, evaluation_sha256 = await _persist_authoritative_activation_evidence(
        app,
        artifact,
        threshold,
        model_artifact_uri=uri,
        model_artifact_sha256=package_sha,
    )

    verifier.register_object(evaluation_uri, b"{}\n", "application/json")
    drift = await client.post(
        f"/api/v1/models/deployments/{deployment_id}/activate",
        headers=_manager_headers("care-anomaly-artifact-drift-1"),
        json={"traffic_percent": 100, "reason": "reject evaluation artifact drift"},
    )
    assert drift.status_code == 409
    assert drift.json()["error"]["code"] == "ANOMALY_ACTIVATION_ARTIFACT_DRIFT"

    original_body = (json.dumps(artifact, ensure_ascii=False, sort_keys=True) + "\n").encode()
    assert (
        verifier.register_object(evaluation_uri, original_body, "application/json")
        == evaluation_sha256
    )
    async with app.state.session_factory() as session, session.begin():
        evaluation = await session.get(BenchmarkEvaluationRun, "eval-final-1")
        assert evaluation is not None
        evaluation.invalidated_at = datetime.now(UTC)
    invalidated = await client.post(
        f"/api/v1/models/deployments/{deployment_id}/activate",
        headers=_manager_headers("care-anomaly-invalidated-1"),
        json={"traffic_percent": 100, "reason": "reject invalidated evaluation"},
    )
    assert invalidated.status_code == 422
    assert invalidated.json()["error"]["code"] == "ANOMALY_ACTIVATION_EVALUATION_INVALID"

    async with app.state.session_factory() as session, session.begin():
        evaluation = await session.get(BenchmarkEvaluationRun, "eval-final-1")
        deployment = await session.get(ModelDeployment, deployment_id)
        assert evaluation is not None and deployment is not None
        evaluation.invalidated_at = None
        changed_gate = json.loads(json.dumps(deployment.evaluation_gate))
        changed_runtime = changed_gate["care_online_runtime"]
        changed_runtime["model_package_sha256"] = "0" * 64
        unsigned_runtime = {
            key: value
            for key, value in changed_runtime.items()
            if key != "runtime_configuration_sha256"
        }
        changed_runtime["runtime_configuration_sha256"] = canonical_online_hash(unsigned_runtime)
        deployment.evaluation_gate = changed_gate
    binding = await client.post(
        f"/api/v1/models/deployments/{deployment_id}/activate",
        headers=_manager_headers("care-anomaly-binding-drift-1"),
        json={"traffic_percent": 100, "reason": "reject model binding drift"},
    )
    assert binding.status_code == 422
    assert binding.json()["error"]["code"] == "ANOMALY_ACTIVATION_BINDING_INVALID"

    async with app.state.session_factory() as session:
        deployment = await session.get(ModelDeployment, deployment_id)
        assert deployment is not None
        assert (deployment.status, deployment.traffic_percent, deployment.activated_at) == (
            "staged",
            0,
            None,
        )
        events = list(
            (
                await session.scalars(
                    select(DomainEvent)
                    .where(DomainEvent.aggregate_id == deployment_id)
                    .order_by(DomainEvent.sequence)
                )
            ).all()
        )
        denials = [event for event in events if event.event_type == "model.activation.denied"]
        assert [event.payload["error_code"] for event in denials] == [
            "ANOMALY_ACTIVATION_ARTIFACT_DRIFT",
            "ANOMALY_ACTIVATION_EVALUATION_INVALID",
            "ANOMALY_ACTIVATION_BINDING_INVALID",
        ]
        assert all(
            event.event_type
            not in {
                "model.activation.authorization-consumed",
                "model.deployment.activated",
            }
            for event in events
        )
