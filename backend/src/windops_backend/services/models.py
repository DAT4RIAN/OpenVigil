from __future__ import annotations

import windops_backend.services.model_activation as _activation
import windops_backend.services.model_inference as _inference
import windops_backend.services.model_registration as _registration
import windops_backend.services.model_runtime_contracts as _contracts
import windops_backend.services.model_serialization as _serialization

__all__ = [
    "ALLOWED_MODEL_CONTENT_TYPES",
    "CARE_ACTIVATION_ARTIFACT_CONTENT_TYPES",
    "CARE_ACTIVATION_GATE_POLICY_VERSION",
    "MAX_CARE_ACTIVATION_ARTIFACT_BYTES",
    "MAX_MODEL_ARTIFACT_BYTES",
    "HttpModelInferenceClient",
    "ModelInferenceClient",
    "activate_deployment",
    "create_deployment",
    "govern_and_activate_deployment",
    "register_model",
    "run_anomaly_inference",
    "run_predictive_inference",
    "select_active_deployment",
    "serialize_deployment",
    "serialize_model",
    "serialize_prediction",
]

ALLOWED_MODEL_CONTENT_TYPES = _contracts.ALLOWED_MODEL_CONTENT_TYPES
MAX_MODEL_ARTIFACT_BYTES = _contracts.MAX_MODEL_ARTIFACT_BYTES
_prediction_locks = _contracts._prediction_locks
CARE_ACTIVATION_GATE_POLICY_VERSION = _contracts.CARE_ACTIVATION_GATE_POLICY_VERSION
CARE_ACTIVATION_ARTIFACT_CONTENT_TYPES = _contracts.CARE_ACTIVATION_ARTIFACT_CONTENT_TYPES
MAX_CARE_ACTIVATION_ARTIFACT_BYTES = _contracts.MAX_CARE_ACTIVATION_ARTIFACT_BYTES
_canonical_json = _contracts._canonical_json
ModelInferenceClient = _contracts.ModelInferenceClient
HttpModelInferenceClient = _contracts.HttpModelInferenceClient
_validate_instance = _contracts._validate_instance

register_model = _registration.register_model
create_deployment = _registration.create_deployment

_metric_passed = _activation._metric_passed
_required_metric = _activation._required_metric
_integer_metric = _activation._integer_metric
_evaluation_document = _activation._evaluation_document
_artifact_approval_lineage = _activation._artifact_approval_lineage
_load_authoritative_activation_evidence = _activation._load_authoritative_activation_evidence
govern_and_activate_deployment = _activation.govern_and_activate_deployment
activate_deployment = _activation.activate_deployment

select_active_deployment = _inference.select_active_deployment
_feature_snapshot = _inference._feature_snapshot
_validate_predictive_output = _inference._validate_predictive_output
_prediction_lock_id = _inference._prediction_lock_id
_claim_prediction_key = _inference._claim_prediction_key
run_predictive_inference = _inference.run_predictive_inference
run_anomaly_inference = _inference.run_anomaly_inference

serialize_model = _serialization.serialize_model
serialize_deployment = _serialization.serialize_deployment
serialize_prediction = _serialization.serialize_prediction
