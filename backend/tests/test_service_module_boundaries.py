from __future__ import annotations

from pathlib import Path

import windops_backend.agents.embeddings as embeddings
import windops_backend.agents.tools as tools
import windops_backend.services.benchmark_catalog as benchmark_catalog
import windops_backend.services.benchmark_catalog_datasets as catalog_datasets
import windops_backend.services.benchmark_catalog_evaluations as catalog_evaluations
import windops_backend.services.benchmark_catalog_events as catalog_events
import windops_backend.services.benchmark_catalog_policy as catalog_policy
import windops_backend.services.benchmark_catalog_replays as catalog_replays
import windops_backend.services.benchmark_metadata as benchmark_metadata
import windops_backend.services.benchmark_metadata_anomaly as metadata_anomaly
import windops_backend.services.benchmark_metadata_evaluation as metadata_evaluation
import windops_backend.services.benchmark_metadata_registration as metadata_registration
import windops_backend.services.benchmark_metadata_replay as metadata_replay
import windops_backend.services.benchmark_metadata_trace as metadata_trace
import windops_backend.services.model_activation as model_activation
import windops_backend.services.model_inference as model_inference
import windops_backend.services.model_registration as model_registration
import windops_backend.services.model_runtime_contracts as model_contracts
import windops_backend.services.model_serialization as model_serialization
import windops_backend.services.models as models
import windops_backend.services.operational_assets as operational_assets
import windops_backend.services.operational_contracts as operational_contracts
import windops_backend.services.operational_diagnosis as operational_diagnosis
import windops_backend.services.operational_maintenance as operational_maintenance
import windops_backend.services.operational_views as operational_views


def test_operational_view_facade_resolves_to_bounded_owners() -> None:
    assert operational_views.OperationalPage is operational_contracts.OperationalPage
    assert operational_views.build_diagnosis_query is operational_diagnosis.build_diagnosis_query
    assert (
        operational_views.build_maintenance_query is operational_maintenance.build_maintenance_query
    )
    assert operational_views.digital_twin_snapshot is operational_assets.digital_twin_snapshot
    assert operational_views.live_report_rows is operational_assets.live_report_rows
    assert operational_views.data_catalog_payload is operational_assets.data_catalog_payload


def test_benchmark_catalog_facade_resolves_to_bounded_owners() -> None:
    assert benchmark_catalog.benchmark_truth_allowed is catalog_policy.benchmark_truth_allowed
    assert benchmark_catalog.benchmark_dataset_page is catalog_datasets.benchmark_dataset_page
    assert benchmark_catalog.benchmark_event_page is catalog_events.benchmark_event_page
    assert benchmark_catalog.benchmark_replay_curve is catalog_replays.benchmark_replay_curve
    assert (
        benchmark_catalog.benchmark_evaluation_page is catalog_evaluations.benchmark_evaluation_page
    )
    assert (
        benchmark_catalog.benchmark_diagnosis_page is catalog_evaluations.benchmark_diagnosis_page
    )


def test_model_service_facade_resolves_to_bounded_owners() -> None:
    assert models.ModelInferenceClient is model_contracts.ModelInferenceClient
    assert models.register_model is model_registration.register_model
    assert models.create_deployment is model_registration.create_deployment
    assert models.govern_and_activate_deployment is model_activation.govern_and_activate_deployment
    assert models.activate_deployment is model_activation.activate_deployment
    assert models.run_predictive_inference is model_inference.run_predictive_inference
    assert models.run_anomaly_inference is model_inference.run_anomaly_inference
    assert models.serialize_model is model_serialization.serialize_model


def test_embedding_api_is_owned_by_dependency_neutral_module() -> None:
    assert tools.EmbeddingProvider is embeddings.EmbeddingProvider
    assert tools.DeterministicTestEmbeddingProvider is embeddings.DeterministicTestEmbeddingProvider
    assert tools.LiteLLMEmbeddingProvider is embeddings.LiteLLMEmbeddingProvider
    assert tools.chunk_embedding_text is embeddings.chunk_embedding_text
    assert tools.embed_texts_with_controls is embeddings.embed_texts_with_controls
    assert tools.EMBEDDING_DIMENSIONS == embeddings.EMBEDDING_DIMENSIONS


def test_benchmark_metadata_facade_resolves_to_transaction_owners() -> None:
    assert (
        benchmark_metadata.register_dataset_version
        is metadata_registration.register_dataset_version
    )
    assert (
        benchmark_metadata.get_or_create_evaluation_run
        is metadata_evaluation.get_or_create_evaluation_run
    )
    assert benchmark_metadata.register_replay_run is metadata_replay.register_replay_run
    assert (
        benchmark_metadata.persist_anomaly_alert_policy_state
        is metadata_anomaly.persist_anomaly_alert_policy_state
    )
    assert benchmark_metadata.build_benchmark_trace is metadata_trace.build_benchmark_trace


def test_broad_service_facades_and_owners_stay_bounded() -> None:
    source_root = Path(__file__).parents[1] / "src" / "windops_backend"
    maximum_lines = {
        "services/operational_views.py": 160,
        "services/benchmark_catalog.py": 100,
        "services/models.py": 100,
        "services/benchmark_metadata.py": 100,
        "agents/tools.py": 1050,
        "services/benchmark_catalog_evaluations.py": 1050,
    }
    for relative_path, limit in maximum_lines.items():
        line_count = len((source_root / relative_path).read_text(encoding="utf-8").splitlines())
        assert line_count <= limit, f"{relative_path} grew to {line_count} lines (limit {limit})"
