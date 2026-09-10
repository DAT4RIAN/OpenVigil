from __future__ import annotations

import windops_backend.services.benchmark_metadata_anomaly as _anomaly
import windops_backend.services.benchmark_metadata_contracts as _contracts
import windops_backend.services.benchmark_metadata_evaluation as _evaluation
import windops_backend.services.benchmark_metadata_registration as _registration
import windops_backend.services.benchmark_metadata_replay as _replay
import windops_backend.services.benchmark_metadata_trace as _trace

__all__ = [
    "build_benchmark_trace",
    "complete_evaluation_run",
    "get_or_create_evaluation_run",
    "persist_anomaly_alert_policy_state",
    "persist_replay_run_progress",
    "record_event_result",
    "record_metric_snapshot",
    "register_benchmark_event",
    "register_benchmark_file",
    "register_dataset_version",
    "register_feature_map",
    "register_quality_report",
    "register_replay_run",
]

_local_locks = _contracts._local_locks
_document_sha256 = _contracts._document_sha256
_advisory_lock_id = _contracts._advisory_lock_id
_same_instant = _contracts._same_instant
_claim_identity = _contracts._claim_identity

register_dataset_version = _registration.register_dataset_version
register_benchmark_file = _registration.register_benchmark_file
register_benchmark_event = _registration.register_benchmark_event
register_feature_map = _registration.register_feature_map
register_quality_report = _registration.register_quality_report

get_or_create_evaluation_run = _evaluation.get_or_create_evaluation_run
record_event_result = _evaluation.record_event_result
record_metric_snapshot = _evaluation.record_metric_snapshot
complete_evaluation_run = _evaluation.complete_evaluation_run

register_replay_run = _replay.register_replay_run
_replay_immutable_identity = _replay._replay_immutable_identity
_request_replay_immutable_identity = _replay._request_replay_immutable_identity
_as_utc = _replay._as_utc
_replay_run_matches_request = _replay._replay_run_matches_request
persist_replay_run_progress = _replay.persist_replay_run_progress

persist_anomaly_alert_policy_state = _anomaly.persist_anomaly_alert_policy_state
build_benchmark_trace = _trace.build_benchmark_trace
