from __future__ import annotations

import gc
import hashlib
import os
import re
import subprocess
import sys
import tracemalloc
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from json import loads
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import httpx
import jwt
import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from windops_backend.config import IdentityAccessScope, Settings
from windops_backend.enums import Environment
from windops_backend.main import create_app
from windops_backend.models import (
    AnomalyAlertPolicyState,
    BenchmarkDatasetVersion,
    BenchmarkEvaluationRun,
    BenchmarkEvent,
    BenchmarkEventResult,
    BenchmarkFeatureMap,
    BenchmarkFile,
    BenchmarkMetricSnapshot,
    BenchmarkQualityReport,
    BenchmarkReplayRun,
    PlatformConfigurationRevision,
    PlatformConfigurationSecurityAudit,
)
from windops_backend.services import operational_views
from windops_backend.services.operational_views import (
    DIAGNOSIS_EVIDENCE_PER_MISSION_LIMIT,
    DIAGNOSIS_EXECUTIONS_PER_MISSION_LIMIT,
    MAINTENANCE_RESOURCES_PER_MISSION_TYPE_LIMIT,
    MAINTENANCE_WEATHER_PER_WORK_ORDER_LIMIT,
    build_diagnosis_priority_bucket_query,
    build_diagnosis_query,
    build_maintenance_query,
    build_maintenance_weather_query,
)

DELEGATION_SECRET = "external-production-gateway-secret-with-at-least-forty-eight-characters"

HEAD_REVISION = "0026_schema_contract_alignment"
PREVIOUS_SUPPORTED_REVISION = "0015_alarm_command_state"
BACKEND_ROOT = Path(__file__).resolve().parents[2]
_DATABASE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{2,62}$")
PERFORMANCE_SAMPLE_COUNT = 100
REQUIRED_TIMESTAMP_COLUMNS = (
    ("agent_executions", "started_at"),
    ("approvals", "created_at"),
    ("asset_health_events", "recorded_at"),
    ("decisions", "created_at"),
    ("decisions", "updated_at"),
    ("evidence", "created_at"),
    ("ingest_receipts", "received_at"),
    ("knowledge_cases", "created_at"),
    ("knowledge_documents", "updated_at"),
    ("missions", "created_at"),
    ("missions", "updated_at"),
    ("resource_reservations", "created_at"),
    ("tenants", "created_at"),
    ("turbines", "updated_at"),
    ("wind_farms", "created_at"),
    ("work_orders", "created_at"),
)

pytestmark = [
    pytest.mark.external_release,
    pytest.mark.skipif(
        os.getenv("WINDOPS_RUN_POSTGRES_CONTRACT_TESTS") != "1",
        reason="requires an isolated PostgreSQL/TimescaleDB/pgvector service",
    ),
]


def _database_url() -> URL:
    value = os.getenv("WINDOPS_POSTGRES_TEST_URL", "").strip()
    if value.startswith("postgres://"):
        value = "postgresql+asyncpg://" + value.removeprefix("postgres://")
    elif value.startswith("postgresql://"):
        value = "postgresql+asyncpg://" + value.removeprefix("postgresql://")
    if not value:
        raise RuntimeError("WINDOPS_POSTGRES_TEST_URL is required")
    return make_url(value)


def _render_url(url: URL) -> str:
    return url.render_as_string(hide_password=False)


async def _recreate_database(admin: AsyncEngine, name: str) -> None:
    if not _DATABASE_IDENTIFIER.fullmatch(name):
        raise ValueError("unsafe PostgreSQL contract database name")
    async with admin.connect() as connection:
        await connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await connection.execute(text(f'CREATE DATABASE "{name}"'))


async def _drop_database(admin: AsyncEngine, name: str) -> None:
    if not _DATABASE_IDENTIFIER.fullmatch(name):
        raise ValueError("unsafe PostgreSQL contract database name")
    async with admin.connect() as connection:
        await connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest_asyncio.fixture
async def migration_database_urls() -> AsyncIterator[tuple[str, str]]:
    base = _database_url()
    admin = create_async_engine(
        base.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )
    suffix = str(os.getpid())
    empty_name = f"windops_empty_{suffix}"
    upgrade_name = f"windops_upgrade_{suffix}"
    await _recreate_database(admin, empty_name)
    await _recreate_database(admin, upgrade_name)
    try:
        yield (
            _render_url(base.set(database=empty_name)),
            _render_url(base.set(database=upgrade_name)),
        )
    finally:
        await _drop_database(admin, empty_name)
        await _drop_database(admin, upgrade_name)
        await admin.dispose()


def _run_alembic(
    database_url: str,
    *arguments: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    environment = {
        **os.environ,
        "WINDOPS_DATABASE_URL": database_url,
        "WINDOPS_ENVIRONMENT": "development",
    }
    return subprocess.run(  # noqa: S603 - fixed interpreter/module and controlled args
        [sys.executable, "-m", "alembic", *arguments],
        cwd=BACKEND_ROOT,
        env=environment,
        check=check,
        capture_output=True,
        text=True,
        timeout=180,
    )


@pytest.mark.asyncio
async def test_empty_database_upgrade_has_production_extensions_and_indexes(
    migration_database_urls: tuple[str, str],
) -> None:
    database_url, _ = migration_database_urls
    _run_alembic(database_url, "upgrade", "head")
    current = _run_alembic(database_url, "current")
    assert HEAD_REVISION in current.stdout

    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            server_version = int(await connection.scalar(text("SHOW server_version_num")) or 0)
            assert 160_000 <= server_version < 170_000
            extensions = dict(
                (
                    await connection.execute(
                        text(
                            "SELECT extname, extversion FROM pg_extension "
                            "WHERE extname IN ('timescaledb', 'vector')"
                        )
                    )
                ).all()
            )
            assert set(extensions) == {"timescaledb", "vector"}
            hypertable = await connection.scalar(
                text(
                    "SELECT hypertable_name FROM timescaledb_information.hypertables "
                    "WHERE hypertable_schema = 'public' AND hypertable_name = 'scada_samples'"
                )
            )
            assert hypertable == "scada_samples"
            vector_type = await connection.scalar(
                text(
                    "SELECT format_type(attribute.atttypid, attribute.atttypmod) "
                    "FROM pg_attribute AS attribute "
                    "JOIN pg_class AS relation ON relation.oid = attribute.attrelid "
                    "WHERE relation.relname = 'knowledge_documents' "
                    "AND attribute.attname = 'embedding'"
                )
            )
            assert vector_type == "vector(1536)"
            hnsw_index = await connection.scalar(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = 'public' "
                    "AND indexname = 'ix_knowledge_documents_embedding_hnsw'"
                )
            )
            assert hnsw_index is not None and "USING hnsw" in hnsw_index
            constraints = set(
                (
                    await connection.scalars(
                        text(
                            "SELECT conname FROM pg_constraint WHERE conname IN "
                            "('uq_command_receipt_subject_scope_target_key', "
                            "'uq_prediction_deployment_turbine_features', "
                            "'uq_platform_config_security_audit_revision')"
                        )
                    )
                ).all()
            )
            assert constraints == {
                "uq_command_receipt_subject_scope_target_key",
                "uq_prediction_deployment_turbine_features",
                "uq_platform_config_security_audit_revision",
            }
            replay_tables = set(
                (
                    await connection.scalars(
                        text(
                            "SELECT table_name FROM information_schema.tables "
                            "WHERE table_schema = 'public' AND table_name IN "
                            "('delegated_request_nonces', 'delegated_request_audits')"
                        )
                    )
                ).all()
            )
            assert replay_tables == {
                "delegated_request_nonces",
                "delegated_request_audits",
            }
            receipt_columns = set(
                (
                    await connection.scalars(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema = 'public' AND table_name = 'command_receipts' "
                            "AND column_name IN ('target', 'replay_count', 'last_replayed_at')"
                        )
                    )
                ).all()
            )
            assert receipt_columns == {"target", "replay_count", "last_replayed_at"}
            bounded_indexes = set(
                (
                    await connection.scalars(
                        text(
                            "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' "
                            "AND indexname = ANY(:names)"
                        ),
                        {
                            "names": [
                                "ix_missions_updated_id",
                                "ix_work_orders_planned_id",
                                "ix_asset_health_turbine_recorded_id",
                                "ix_resources_type_status_id",
                                "ix_reservations_resource_created_id",
                                "ix_weather_farm_starts_ends_id",
                                "ix_weather_farm_suitable_starts_ends_id",
                                "ix_alarms_severity_id",
                                "ix_turbines_health_id",
                            ]
                        },
                    )
                ).all()
            )
            assert bounded_indexes == {
                "ix_missions_updated_id",
                "ix_work_orders_planned_id",
                "ix_asset_health_turbine_recorded_id",
                "ix_resources_type_status_id",
                "ix_reservations_resource_created_id",
                "ix_weather_farm_starts_ends_id",
                "ix_weather_farm_suitable_starts_ends_id",
                "ix_alarms_severity_id",
                "ix_turbines_health_id",
            }
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_schema_contract_alignment_backfills_and_matches_orm(
    migration_database_urls: tuple[str, str],
) -> None:
    _, database_url = migration_database_urls
    _run_alembic(database_url, "upgrade", "0025_benchmark_event_score_scope")
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE tenants SET created_at = NULL WHERE id = 'tenant-east-china'")
            )

        _run_alembic(database_url, "upgrade", "head")
        assert HEAD_REVISION in _run_alembic(database_url, "current").stdout
        async with engine.connect() as connection:
            backfilled_at = await connection.scalar(
                text("SELECT created_at FROM tenants WHERE id = 'tenant-east-china'")
            )
            assert backfilled_at is not None
            for table_name, column_name in REQUIRED_TIMESTAMP_COLUMNS:
                nullable = await connection.scalar(
                    text(
                        "SELECT is_nullable FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = :table_name "
                        "AND column_name = :column_name"
                    ),
                    {"table_name": table_name, "column_name": column_name},
                )
                assert nullable == "NO", f"{table_name}.{column_name} remained nullable"

            index_definitions = dict(
                (
                    await connection.execute(
                        text(
                            "SELECT indexname, indexdef FROM pg_indexes "
                            "WHERE schemaname = 'public' AND indexname = ANY(:names)"
                        ),
                        {
                            "names": [
                                "ix_decisions_mission_id",
                                "ix_field_task_evidence_task_id",
                                "ix_knowledge_documents_tenant_scope",
                                "ix_scada_turbine_variable_observed",
                            ]
                        },
                    )
                ).all()
            )
            assert "UNIQUE INDEX" in index_definitions["ix_decisions_mission_id"]
            assert "UNIQUE INDEX" not in index_definitions["ix_field_task_evidence_task_id"]
            assert (
                "tenant_id, wind_farm_id, turbine_id, data_scope"
                in index_definitions["ix_knowledge_documents_tenant_scope"]
            )
            assert "observed_at DESC" in index_definitions["ix_scada_turbine_variable_observed"]

        check = _run_alembic(database_url, "check")
        assert "No new upgrade operations detected" in check.stdout + check.stderr

        _run_alembic(database_url, "downgrade", "0025_benchmark_event_score_scope")
        async with engine.connect() as connection:
            nullable = await connection.scalar(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'tenants' "
                    "AND column_name = 'created_at'"
                )
            )
            assert nullable == "YES"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_care_metadata_upgrade_preserves_legacy_rows_and_downgrade_fails_closed(
    migration_database_urls: tuple[str, str],
) -> None:
    _, database_url = migration_database_urls
    _run_alembic(database_url, "upgrade", "0023_bounded_weather_selection")
    engine = create_async_engine(database_url, pool_pre_ping=True)
    legacy_alarm_id = "00000000-0000-0000-0000-000000002401"
    prediction_id = "00000000-0000-0000-0000-000000002402"
    deployment_id = "00000000-0000-0000-0000-000000002403"
    model_only_alarm_id = "00000000-0000-0000-0000-000000002404"
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO wind_farms (id, tenant_id, name, capacity_mw) VALUES "
                    "('WF-CARE-H002', 'tenant-east-china', 'CARE migration farm', 1.0)"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO turbines (id, wind_farm_id, model, status, health_score) "
                    "VALUES ('WT-CARE-H002', 'WF-CARE-H002', 'legacy', 'running', 100)"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO ingest_receipts "
                    "(source_event_id, source_id, payload_hash, disposition) VALUES "
                    "('CARE-H002-LEGACY-RECEIPT', 'scada-default', :sha, 'accepted')"
                ),
                {"sha": "a" * 64},
            )
            await connection.execute(
                text(
                    "INSERT INTO alarms "
                    "(id, turbine_id, source_event_id, code, subsystem, title, triggered_at) "
                    "VALUES (:id, 'WT-CARE-H002', 'CARE-H002-LEGACY-RECEIPT', "
                    "'LEGACY', 'benchmark', 'legacy alarm', now())"
                ),
                {"id": legacy_alarm_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO registered_models "
                    "(id, name, version, kind, status, artifact_uri, artifact_sha256, "
                    "content_type, content_size_bytes, input_schema, output_schema, metrics, "
                    "description, created_by) VALUES "
                    "('CARE-H002-MODEL', 'CARE migration model', '1.0.0', 'predictive', "
                    "'active', 'minio://care/models/legacy.onnx', :sha, 'application/onnx', "
                    '10, \'{"type":"object"}\'::jsonb, \'{"type":"object"}\'::jsonb, '
                    "'{}'::jsonb, 'legacy migration fixture', 'migration-contract')"
                ),
                {"sha": "b" * 64},
            )
            await connection.execute(
                text(
                    "INSERT INTO model_deployments "
                    "(id, model_id, target_id, stage, status, traffic_percent, evaluation_gate, "
                    "deployed_by) VALUES (:id, 'CARE-H002-MODEL', 'legacy-target', "
                    "'production', 'active', 100, '{}'::jsonb, 'migration-contract')"
                ),
                {"id": deployment_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO model_predictions "
                    "(id, model_id, deployment_id, turbine_id, feature_observed_at, input_digest, "
                    "input_snapshot, output, status, latency_ms, requested_by) VALUES "
                    "(:id, 'CARE-H002-MODEL', :deployment_id, 'WT-CARE-H002', now(), :sha, "
                    "'{}'::jsonb, '{}'::jsonb, 'succeeded', 1, 'migration-contract')"
                ),
                {"id": prediction_id, "deployment_id": deployment_id, "sha": "c" * 64},
            )

        _run_alembic(database_url, "upgrade", "head")
        assert HEAD_REVISION in _run_alembic(database_url, "current").stdout
        expected_tables = {
            "benchmark_dataset_versions",
            "benchmark_files",
            "benchmark_events",
            "benchmark_feature_maps",
            "benchmark_quality_reports",
            "benchmark_evaluation_runs",
            "benchmark_event_results",
            "benchmark_metric_snapshots",
            "benchmark_replay_runs",
            "anomaly_alert_policy_states",
        }
        async with engine.connect() as connection:
            actual_tables = set(
                await connection.scalars(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public' AND "
                        "(table_name LIKE 'benchmark_%' "
                        "OR table_name = 'anomaly_alert_policy_states')"
                    )
                )
            )
            assert expected_tables.issubset(actual_tables)
            care_models = (
                BenchmarkDatasetVersion,
                BenchmarkFile,
                BenchmarkEvent,
                BenchmarkFeatureMap,
                BenchmarkQualityReport,
                BenchmarkEvaluationRun,
                BenchmarkEventResult,
                BenchmarkMetricSnapshot,
                BenchmarkReplayRun,
                AnomalyAlertPolicyState,
            )
            for model in care_models:
                database_columns = set(
                    await connection.scalars(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema = 'public' AND table_name = :table_name"
                        ),
                        {"table_name": model.__tablename__},
                    )
                )
                assert database_columns == set(model.__table__.columns.keys())
            care_constraints = set(
                await connection.scalars(
                    text(
                        "SELECT constraint_name FROM information_schema.table_constraints "
                        "WHERE table_schema = 'public'"
                    )
                )
            )
            assert {
                "uq_registered_model_id_version",
                "fk_benchmark_evaluation_registered_model_version",
                "fk_benchmark_replay_registered_model_version",
                "uq_benchmark_evaluation_input_identity",
                "uq_benchmark_event_result_run_event",
                "ck_benchmark_replay_deployment_model",
                "ck_model_predictions_anomaly_structure",
                "ck_alarms_has_source",
                "uq_alarms_model_prediction_id",
            }.issubset(care_constraints)
            care_indexes = set(
                await connection.scalars(
                    text(
                        "SELECT indexname FROM pg_indexes "
                        "WHERE schemaname = 'public' AND "
                        "(tablename LIKE 'benchmark_%' OR tablename = 'model_predictions')"
                    )
                )
            )
            assert {
                "ix_benchmark_datasets_tenant_status",
                "ix_benchmark_evaluation_model_created",
                "ix_benchmark_replay_event_status",
                "ix_model_predictions_benchmark_replay_created",
                "ix_model_predictions_benchmark_evaluation_created",
            }.issubset(care_indexes)
            legacy_alarm = (
                await connection.execute(
                    text("SELECT source_event_id, model_prediction_id FROM alarms WHERE id = :id"),
                    {"id": legacy_alarm_id},
                )
            ).one()
            assert tuple(legacy_alarm) == ("CARE-H002-LEGACY-RECEIPT", None)
            prediction_kind = await connection.scalar(
                text("SELECT prediction_kind FROM model_predictions WHERE id = :id"),
                {"id": prediction_id},
            )
            assert prediction_kind == "predictive"

        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO alarms "
                    "(id, turbine_id, source_event_id, model_prediction_id, code, subsystem, "
                    "title, triggered_at) VALUES (:id, 'WT-CARE-H002', NULL, :prediction_id, "
                    "'MODEL', 'benchmark', 'model-only alarm', now())"
                ),
                {"id": model_only_alarm_id, "prediction_id": prediction_id},
            )
        failed_downgrade = _run_alembic(
            database_url, "downgrade", "0023_bounded_weather_selection", check=False
        )
        assert failed_downgrade.returncode != 0
        assert "model-only alarms exist" in (failed_downgrade.stdout + failed_downgrade.stderr)
        assert HEAD_REVISION in _run_alembic(database_url, "current").stdout

        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM alarms WHERE id = :id"), {"id": model_only_alarm_id}
            )
        _run_alembic(database_url, "downgrade", "0023_bounded_weather_selection")
        assert "0023_bounded_weather_selection" in _run_alembic(database_url, "current").stdout
        async with engine.connect() as connection:
            source_nullable = await connection.scalar(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'alarms' AND column_name = 'source_event_id'"
                )
            )
            assert source_nullable == "NO"
            assert (
                await connection.scalar(
                    text("SELECT source_event_id FROM alarms WHERE id = :id"),
                    {"id": legacy_alarm_id},
                )
                == "CARE-H002-LEGACY-RECEIPT"
            )
        _run_alembic(database_url, "upgrade", "head")

        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO alarms "
                        "(id, turbine_id, source_event_id, model_prediction_id, code, subsystem, "
                        "title, triggered_at) VALUES "
                        "('00000000-0000-0000-0000-000000002405', 'WT-CARE-H002', NULL, NULL, "
                        "'INVALID', 'benchmark', 'source-less alarm', now())"
                    )
                )
        with pytest.raises(IntegrityError):
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO model_predictions "
                        "(id, model_id, deployment_id, turbine_id, feature_observed_at, "
                        "prediction_kind, input_digest, input_snapshot, output, status, "
                        "latency_ms, requested_by) VALUES "
                        "('00000000-0000-0000-0000-000000002406', 'CARE-H002-MODEL', "
                        ":deployment_id, 'WT-CARE-H002', now() + interval '1 minute', 'anomaly', "
                        ":sha, '{}'::jsonb, '{}'::jsonb, 'succeeded', 1, 'migration-contract')"
                    ),
                    {"deployment_id": deployment_id, "sha": "d" * 64},
                )
    finally:
        await engine.dispose()

    _run_alembic(database_url, "downgrade", "0022_diagnosis_priority_indexes")
    downgraded = _run_alembic(database_url, "current")
    assert "0022_diagnosis_priority_indexes" in downgraded.stdout
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    text("SELECT to_regclass('public.ix_weather_farm_suitable_starts_ends_id')")
                )
                is None
            )
    finally:
        await engine.dispose()

    _run_alembic(database_url, "upgrade", "head")
    upgraded = _run_alembic(database_url, "current")
    assert HEAD_REVISION in upgraded.stdout


@pytest.mark.asyncio
async def test_previous_supported_upgrade_preserves_data_and_retries_after_failure(
    migration_database_urls: tuple[str, str],
) -> None:
    _, database_url = migration_database_urls
    _run_alembic(database_url, "upgrade", PREVIOUS_SUPPORTED_REVISION)
    controlled_secret = "migration-fixture-credential"
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO wind_farms (id, name, capacity_mw) "
                    "VALUES ('WF-UPGRADE', 'Upgrade compatibility farm', 12.5)"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO turbines (id, wind_farm_id, model) "
                    "VALUES ('WT-UPGRADE', 'WF-UPGRADE', 'GW-UPGRADE')"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO knowledge_documents "
                    "(id, title, document_type, body, citation_uri, created_by) "
                    "VALUES ('KB-UPGRADE', 'Upgrade document', 'procedure', "
                    "'Representative retained content', 'minio://upgrade/document', "
                    "'migration-contract')"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO platform_configuration_revisions "
                    "(id, configuration_key, revision, value, secret_reference, active, "
                    "reason, created_by) VALUES "
                    "('CFG-UPGRADE-SECRET', 'backup_policy', 1, "
                    "CAST(:value AS JSONB), NULL, TRUE, 'legacy compatibility fixture', "
                    "'migration-contract')"
                ),
                {
                    "value": (
                        f'{{"rpo_minutes":15,"rto_minutes":60,"api_token":"{controlled_secret}"}}'
                    )
                },
            )
    finally:
        await engine.dispose()

    await _verify_previous_supported_upgrade(database_url, controlled_secret)


def _plan_nodes(plan: dict[str, object]) -> list[dict[str, object]]:
    nodes = [plan]
    for child in plan.get("Plans", []):
        if isinstance(child, dict):
            nodes.extend(_plan_nodes(child))
    return nodes


def _literal_query(statement: object) -> text:
    compiled = statement.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    return text(str(compiled))


def _percentile(samples: list[float], percentile: float) -> float:
    if not samples:
        raise ValueError("percentile requires at least one sample")
    if not 0 <= percentile <= 1:
        raise ValueError("percentile must be between zero and one")
    ordered = sorted(samples)
    position = (len(ordered) - 1) * percentile
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    weight = position - lower_index
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * weight


@pytest.mark.asyncio
async def test_bounded_collection_plans_and_latency_at_100k_rows(
    migration_database_urls: tuple[str, str],
    record_testsuite_property: Callable[[str, object], None],
) -> None:
    database_url, _ = migration_database_urls
    _run_alembic(database_url, "upgrade", "head")
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO wind_farms (id, tenant_id, name, capacity_mw) VALUES "
                    "('WF-PERF', 'tenant-east-china', 'Performance contract farm', 500.0)"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO turbines (id, wind_farm_id, model, health_score) "
                    "SELECT 'WT-PERF-' || lpad(series::text, 3, '0'), 'WF-PERF', "
                    "'PERF-MODEL', 80 + (series % 20) FROM generate_series(0, 99) AS series"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO ingest_receipts "
                    "(source_event_id, source_id, payload_hash, disposition) "
                    "SELECT 'PERF-EVENT-' || lpad(series::text, 10, '0'), 'scada-default', "
                    "repeat('a', 64), 'accepted' FROM generate_series(1, 100000) AS series"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO alarms "
                    "(id, turbine_id, source_event_id, code, subsystem, title, severity, "
                    "status, triggered_at) SELECT "
                    "'PERF-ALARM-' || lpad(series::text, 10, '0'), "
                    "'WT-PERF-' || lpad((series % 100)::text, 3, '0'), "
                    "'PERF-EVENT-' || lpad(series::text, 10, '0'), 'PERF', 'bearing', "
                    "'Performance alarm', CASE WHEN series % 20 = 0 THEN 'critical' "
                    "ELSE 'major' END, 'open', now() - series * interval '1 second' "
                    "FROM generate_series(1, 100000) AS series"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO missions "
                    "(id, alarm_id, turbine_id, title, status, public_state, "
                    "created_at, updated_at) "
                    "SELECT 'PERF-MISSION-' || lpad(series::text, 10, '0'), "
                    "'PERF-ALARM-' || lpad(series::text, 10, '0'), "
                    "'WT-PERF-' || lpad((series % 100)::text, 3, '0'), "
                    "'Performance mission', CASE WHEN series % 2 = 0 THEN 'under_review' "
                    "ELSE 'diagnosed' END, jsonb_build_object('diagnosis', "
                    "jsonb_build_object('confidence', 0.8)), now() - series * interval '1 second', "
                    "now() - series * interval '1 second' "
                    "FROM generate_series(1, 100000) AS series"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO approvals "
                    "(id, mission_id, mission_revision, action, approver, reason) SELECT "
                    "'PERF-APPROVAL-' || lpad(series::text, 10, '0'), "
                    "'PERF-MISSION-' || lpad(series::text, 10, '0'), 1, 'approve', "
                    "'performance-contract', 'performance contract' "
                    "FROM generate_series(1, 100000) AS series"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO work_orders "
                    "(id, mission_id, approval_id, turbine_id, title, selected_alternative_id, "
                    "selected_action, status, priority, assigned_team, planned_start, deadline, "
                    "estimated_duration_hours) SELECT "
                    "'PERF-WO-' || lpad(series::text, 10, '0'), "
                    "'PERF-MISSION-' || lpad(series::text, 10, '0'), "
                    "'PERF-APPROVAL-' || lpad(series::text, 10, '0'), "
                    "'WT-PERF-' || lpad((series % 100)::text, 3, '0'), "
                    "'Performance work order', 'PERF-ALT', 'Inspect', 'scheduled', 'high', "
                    "'PERF-TEAM', now() + (series % 10000) * interval '1 minute', "
                    "now() + (series % 10000 + 240) * interval '1 minute', 4.0 "
                    "FROM generate_series(1, 100000) AS series"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO asset_health_events "
                    "(id, turbine_id, score, status, reason, recorded_at) SELECT "
                    "'PERF-HEALTH-' || lpad(series::text, 10, '0'), "
                    "'WT-PERF-' || lpad((series % 100)::text, 3, '0'), 80.0, 'watch', "
                    "'Performance health event', now() - series * interval '1 second' "
                    "FROM generate_series(1, 100000) AS series"
                )
            )
            for table_name in ("missions", "work_orders", "asset_health_events"):
                await connection.execute(text(f"ANALYZE {table_name}"))

        diagnosis_plan = build_diagnosis_query(
            tenant_id="tenant-east-china",
            wind_farm_id="WF-PERF",
            sort_mode="priority-desc",
            offset=0,
            limit=64,
        )
        diagnosis_filtered_plan = build_diagnosis_query(
            query="performance",
            tenant_id="tenant-east-china",
            turbine_id="WT-PERF-001",
            status_filter="scheduled",
            risk="high",
            sort_mode="confidence-desc",
            offset=128,
            limit=64,
        )
        maintenance_plan = build_maintenance_query(
            dialect_name="postgresql",
            tenant_id="tenant-east-china",
            wind_farm_id="WF-PERF",
            sort_mode="start-asc",
            offset=0,
            limit=50,
        )
        maintenance_filtered_plan = build_maintenance_query(
            dialect_name="postgresql",
            query="performance",
            tenant_id="tenant-east-china",
            turbine_id="WT-PERF-001",
            status_filter="at-risk",
            risk="high",
            team="PERF-TEAM",
            sort_mode="risk-desc",
            offset=100,
            limit=50,
        )
        async with engine.begin() as connection:
            diagnosis_default_ids = list(
                (
                    await connection.execute(
                        build_diagnosis_priority_bucket_query(
                            diagnosis_plan,
                            risk_bucket="critical",
                            fetch_limit=64,
                        )
                    )
                )
                .scalars()
                .all()
            )
            diagnosis_filtered_ids = list(
                (await connection.execute(diagnosis_filtered_plan.page)).scalars().all()
            )
            diagnosis_mission_ids = diagnosis_default_ids + diagnosis_filtered_ids
            work_order_default_ids = list(
                (await connection.execute(maintenance_plan.page)).scalars().all()
            )
            work_order_filtered_ids = list(
                (await connection.execute(maintenance_filtered_plan.page)).scalars().all()
            )
            assert len(diagnosis_default_ids) == 64
            assert len(diagnosis_filtered_ids) == 64
            assert len(work_order_default_ids) == 50
            assert len(work_order_filtered_ids) == 50
            work_order_ids = work_order_default_ids + work_order_filtered_ids
            work_order_ids = sorted(set(work_order_ids))
            maintenance_mission_ids = list(
                (
                    await connection.execute(
                        text(
                            "SELECT mission_id FROM work_orders "
                            "WHERE id = ANY(CAST(:work_order_ids AS text[]))"
                        ),
                        {"work_order_ids": work_order_ids},
                    )
                ).scalars()
            )
            high_fanout_mission_ids = sorted(
                set(diagnosis_mission_ids) | set(maintenance_mission_ids)
            )
            assert diagnosis_mission_ids
            assert work_order_ids
            assert high_fanout_mission_ids

            await connection.execute(
                text(
                    "INSERT INTO evidence "
                    "(id, mission_id, source_key, evidence_type, summary, source_refs, metrics, "
                    "created_at) SELECT "
                    "'PERF-E-' || md5(parent.mission_id || ':' || fanout::text), "
                    "parent.mission_id, 'fanout-' || fanout::text, 'performance_contract', "
                    "'Bounded evidence row ' || fanout::text, '[]'::jsonb, '{}'::jsonb, "
                    "now() - fanout * interval '1 second' "
                    "FROM unnest(CAST(:mission_ids AS text[])) AS parent(mission_id) "
                    "CROSS JOIN generate_series(1, 24) AS fanout"
                ),
                {"mission_ids": high_fanout_mission_ids},
            )
            await connection.execute(
                text(
                    "INSERT INTO agent_executions "
                    "(id, mission_id, node, agent_role, status, input_refs, public_output, "
                    "tool_calls, latency_ms, provider, token_usage, evaluation_result, "
                    "degradation_policy, started_at, completed_at) SELECT "
                    "'PEX-' || md5(parent.mission_id || ':' || fanout::text), "
                    "parent.mission_id, 'performance_contract', 'diagnosis_agent', 'succeeded', "
                    "'{}'::jsonb, jsonb_build_object('summary', "
                    "'Bounded execution row ' || fanout::text), "
                    "jsonb_build_array(jsonb_build_object('tool', 'query_scada', "
                    "'status', 'recorded')), 10, 'performance-contract', '{}'::jsonb, "
                    "'{}'::jsonb, '{}'::jsonb, now() - fanout * interval '1 second', "
                    "now() - fanout * interval '1 second' "
                    "FROM unnest(CAST(:mission_ids AS text[])) AS parent(mission_id) "
                    "CROSS JOIN generate_series(1, 24) AS fanout"
                ),
                {"mission_ids": high_fanout_mission_ids},
            )
            await connection.execute(
                text(
                    "INSERT INTO work_order_tasks "
                    "(id, work_order_id, sequence, title, schema_version, measurement_schema, "
                    "status) SELECT md5(parent.work_order_id || ':' || fanout::text), "
                    "parent.work_order_id, fanout, 'Performance task ' || fanout::text, "
                    "'performance-v1', '{\"type\":\"object\"}'::jsonb, "
                    "CASE WHEN fanout % 2 = 0 THEN 'completed' ELSE 'pending' END "
                    "FROM unnest(CAST(:work_order_ids AS text[])) AS parent(work_order_id) "
                    "CROSS JOIN generate_series(1, 80) AS fanout"
                ),
                {"work_order_ids": work_order_ids},
            )
            await connection.execute(
                text(
                    "INSERT INTO resources "
                    "(id, resource_type, name, quantity, status, attributes, updated_at) SELECT "
                    "'PERF-R-' || md5(parent.mission_id || ':' || kind.resource_type || ':' || "
                    "fanout::text), kind.resource_type, "
                    "'Performance ' || kind.resource_type || ' ' || fanout::text, 1, "
                    "'reserved', '{}'::jsonb, now() - fanout * interval '1 second' "
                    "FROM unnest(CAST(:mission_ids AS text[])) AS parent(mission_id) "
                    "CROSS JOIN unnest(ARRAY['crew','vessel','spare_part','tool']::text[]) "
                    "AS kind(resource_type) CROSS JOIN generate_series(1, 6) AS fanout"
                ),
                {"mission_ids": maintenance_mission_ids},
            )
            await connection.execute(
                text(
                    "INSERT INTO resource_reservations "
                    "(id, mission_id, resource_id, quantity, created_at) SELECT "
                    "'PR-' || md5(parent.mission_id || ':' || kind.resource_type || ':' || "
                    "fanout::text), parent.mission_id, "
                    "'PERF-R-' || md5(parent.mission_id || ':' || kind.resource_type || ':' || "
                    "fanout::text), 1, now() - fanout * interval '1 second' "
                    "FROM unnest(CAST(:mission_ids AS text[])) AS parent(mission_id) "
                    "CROSS JOIN unnest(ARRAY['crew','vessel','spare_part','tool']::text[]) "
                    "AS kind(resource_type) CROSS JOIN generate_series(1, 6) AS fanout"
                ),
                {"mission_ids": maintenance_mission_ids},
            )
            await connection.execute(
                text(
                    "INSERT INTO weather_windows "
                    "(id, wind_farm_id, starts_at, ends_at, wind_speed_ms, wave_height_m, "
                    "suitable, attributes) SELECT "
                    "'PERF-WEATHER-' || lpad(series::text, 10, '0'), 'WF-PERF', "
                    "now() - interval '1 hour', now() + interval '30 days', 30.0, 5.0, "
                    "false, jsonb_build_object('performance_contract', true) "
                    "FROM generate_series(1, 20000) AS series"
                )
            )
            for table_name in (
                "evidence",
                "agent_executions",
                "work_order_tasks",
                "resources",
                "resource_reservations",
                "weather_windows",
            ):
                await connection.execute(text(f"ANALYZE {table_name}"))

        diagnosis_sql = _literal_query(
            build_diagnosis_priority_bucket_query(
                diagnosis_plan,
                risk_bucket="critical",
                fetch_limit=64,
            )
        )
        diagnosis_filtered_sql = _literal_query(diagnosis_filtered_plan.page)
        work_order_sql = _literal_query(maintenance_plan.page)
        work_order_filtered_sql = _literal_query(maintenance_filtered_plan.page)
        weather_limit_one_query = build_maintenance_weather_query(
            work_order_ids=work_order_default_ids[:1],
            dialect_name="postgresql",
        )
        weather_limit_fifty_query = build_maintenance_weather_query(
            work_order_ids=work_order_default_ids,
            dialect_name="postgresql",
        )
        weather_limit_fifty_sql = _literal_query(weather_limit_fifty_query)
        health_sql = text(
            "SELECT event.id, event.turbine_id, event.recorded_at FROM "
            "unnest(CAST(:turbine_ids AS text[])) AS selected(turbine_id) "
            "CROSS JOIN LATERAL (SELECT id, turbine_id, recorded_at "
            "FROM asset_health_events WHERE turbine_id = selected.turbine_id "
            "ORDER BY recorded_at DESC, id DESC LIMIT 2) AS event"
        )
        turbine_ids = [f"WT-PERF-{index:03d}" for index in range(10)]
        async with engine.connect() as connection:
            weather_limit_one_rows = (await connection.execute(weather_limit_one_query)).all()
            weather_limit_fifty_rows = (await connection.execute(weather_limit_fifty_query)).all()
            assert len(weather_limit_one_rows) == 1
            assert len(weather_limit_fifty_rows) == 50
            assert weather_limit_one_rows[0][-1] is True
            assert all(row[-1] is True for row in weather_limit_fifty_rows)
            plans: dict[str, dict[str, object]] = {}
            for name, sql, parameters in (
                ("diagnosis", diagnosis_sql, {}),
                ("diagnosis_filtered", diagnosis_filtered_sql, {}),
                ("work_order", work_order_sql, {}),
                ("work_order_filtered", work_order_filtered_sql, {}),
                ("weather_selection", weather_limit_fifty_sql, {}),
                ("health", health_sql, {"turbine_ids": turbine_ids}),
            ):
                explained = await connection.scalar(
                    text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql.text}"),
                    parameters,
                )
                if isinstance(explained, str):
                    explained = loads(explained)
                assert isinstance(explained, list) and explained
                plans[name] = explained[0]["Plan"]

            diagnosis_nodes = _plan_nodes(plans["diagnosis"])
            diagnosis_filtered_nodes = _plan_nodes(plans["diagnosis_filtered"])
            work_order_nodes = _plan_nodes(plans["work_order"])
            work_order_filtered_nodes = _plan_nodes(plans["work_order_filtered"])
            weather_selection_nodes = _plan_nodes(plans["weather_selection"])
            health_nodes = _plan_nodes(plans["health"])
            diagnosis_sorts = [node for node in diagnosis_nodes if node.get("Node Type") == "Sort"]
            work_order_sorts = [
                node for node in work_order_nodes if node.get("Node Type") == "Sort"
            ]
            # The production priority/risk expressions are computed across joined
            # alarm/turbine rows, so PostgreSQL may need an in-memory sort.  Reject
            # every disk sort; an index-ordered plan is also valid where available.
            assert all(
                node.get("Sort Method") in {"top-N heapsort", "quicksort"}
                and node.get("Sort Space Type") == "Memory"
                for node in diagnosis_sorts
            ), [(node.get("Sort Method"), node.get("Sort Space Type")) for node in diagnosis_sorts]
            assert any(
                node.get("Index Name") == "ix_alarms_severity_id" for node in diagnosis_nodes
            )
            assert any(
                node.get("Index Name") == "ix_missions_turbine_id"
                for node in diagnosis_filtered_nodes
            )
            assert all(
                node.get("Sort Method") in {"top-N heapsort", "quicksort"}
                and node.get("Sort Space Type") == "Memory"
                for node in work_order_sorts
            ), [(node.get("Sort Method"), node.get("Sort Space Type")) for node in work_order_sorts]
            assert any(
                node.get("Index Name") == "ix_work_orders_turbine_id"
                for node in work_order_filtered_nodes
            )
            assert any(
                node.get("Index Name") == "ix_weather_farm_suitable_starts_ends_id"
                for node in weather_selection_nodes
            ), [(node.get("Node Type"), node.get("Index Name")) for node in weather_selection_nodes]
            assert diagnosis_filtered_nodes
            assert work_order_filtered_nodes
            assert any(
                node.get("Index Name") == "ix_asset_health_turbine_recorded_id"
                for node in health_nodes
            )

            for name in (
                "diagnosis",
                "diagnosis_filtered",
                "work_order",
                "work_order_filtered",
                "weather_selection",
            ):
                record_testsuite_property(
                    f"{name}_page_sql_ms",
                    round(float(plans[name].get("Actual Total Time", 0.0)), 3),
                )

        settings = Settings(
            environment=Environment.TEST,
            database_url=database_url,
            schema_bootstrap=False,
            demo_seed=False,
            agent_mode="deterministic",
            test_auth_bypass_enabled=True,
            outbox_inline_drain=True,
            knowledge_graph_backend="memory",
        )
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            sql_metrics: dict[str, float | int] = {"count": 0, "milliseconds": 0.0}
            query_starts: dict[int, tuple[float, str]] = {}
            statement_samples: list[tuple[str, float]] = []

            def statement_label(statement: str) -> str:
                normalized = " ".join(statement.lower().split())
                for marker, label in (
                    ("diagnosis_priority_candidates", "priority_page"),
                    ("diagnosis_page_turbine", "page_hydration"),
                    (" from evidence ", "evidence_fanout"),
                    (" from agent_executions ", "execution_fanout"),
                    (" from work_order_tasks ", "task_aggregate"),
                    (" from resource_reservations ", "resource_fanout"),
                    (" from agent_executions", "real_inference"),
                ):
                    if marker in normalized:
                        return label
                if "count(" in normalized:
                    return "count"
                return "other"

            def before_cursor_execute(
                _connection: object,
                _cursor: object,
                _statement: str,
                _parameters: object,
                context: object,
                _executemany: bool,
            ) -> None:
                sql_metrics["count"] = int(sql_metrics["count"]) + 1
                label = statement_label(_statement)
                query_starts[id(context)] = (perf_counter(), label)

            def after_cursor_execute(
                _connection: object,
                _cursor: object,
                _statement: str,
                _parameters: object,
                context: object,
                _executemany: bool,
            ) -> None:
                started_query = query_starts.pop(id(context), None)
                if started_query is not None:
                    started, label = started_query
                    duration_ms = (perf_counter() - started) * 1_000
                    sql_metrics["milliseconds"] = float(sql_metrics["milliseconds"]) + duration_ms
                    statement_samples.append((label, duration_ms))

            sync_engine = app.state.engine.sync_engine
            event.listen(sync_engine, "before_cursor_execute", before_cursor_execute)
            event.listen(sync_engine, "after_cursor_execute", after_cursor_execute)
            common_headers = {
                "X-WindOps-Test-Principal": "performance-contract",
                "X-WindOps-Test-Role": "test_system",
            }
            scoped_headers = {
                "X-WindOps-Test-Tenant-Ids": "tenant-east-china",
                "X-WindOps-Test-Wind-Farm-Ids": "WF-PERF",
            }
            tenant_headers = {
                "X-WindOps-Test-Tenant-Ids": "tenant-east-china",
            }
            scenarios: tuple[
                tuple[str, str, dict[str, object], dict[str, str], int, int, str], ...
            ] = (
                (
                    "diagnosis",
                    "/api/v1/diagnoses",
                    {"sort": "priority-desc", "offset": 0, "limit": 64},
                    scoped_headers,
                    8,
                    64,
                    "diagnosis",
                ),
                (
                    "diagnosis_filtered",
                    "/api/v1/diagnoses",
                    {
                        "q": "performance",
                        "turbineId": "WT-PERF-001",
                        "status": "scheduled",
                        "risk": "high",
                        "sort": "confidence-desc",
                        "offset": 128,
                        "limit": 64,
                    },
                    tenant_headers,
                    8,
                    64,
                    "diagnosis",
                ),
                (
                    "work_order",
                    "/api/v1/maintenance-plans",
                    {"sort": "start-asc", "offset": 0, "limit": 50},
                    scoped_headers,
                    9,
                    50,
                    "maintenance",
                ),
                (
                    "work_order_weather_limit_one",
                    "/api/v1/maintenance-plans",
                    {"sort": "start-asc", "offset": 0, "limit": 1},
                    scoped_headers,
                    9,
                    1,
                    "maintenance",
                ),
                (
                    "work_order_filtered",
                    "/api/v1/maintenance-plans",
                    {
                        "q": "performance",
                        "turbineId": "WT-PERF-001",
                        "status": "at-risk",
                        "risk": "high",
                        "team": "PERF-TEAM",
                        "sort": "risk-desc",
                        "offset": 100,
                        "limit": 50,
                    },
                    tenant_headers,
                    9,
                    50,
                    "maintenance",
                ),
            )

            def reset_sql_metrics() -> None:
                sql_metrics["count"] = 0
                sql_metrics["milliseconds"] = 0.0
                query_starts.clear()
                statement_samples.clear()

            try:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url="http://test",
                    headers=common_headers,
                ) as client:
                    with (
                        patch.object(
                            operational_views,
                            "build_diagnosis_query",
                            wraps=operational_views.build_diagnosis_query,
                        ) as diagnosis_builder,
                        patch.object(
                            operational_views,
                            "build_maintenance_query",
                            wraps=operational_views.build_maintenance_query,
                        ) as maintenance_builder,
                    ):
                        for (
                            name,
                            path,
                            parameters,
                            scope_headers,
                            query_budget,
                            expected_rows,
                            view_kind,
                        ) in scenarios:
                            reset_sql_metrics()
                            warmup = await client.get(
                                path,
                                params=parameters,
                                headers=scope_headers,
                            )
                            assert warmup.status_code == 200, warmup.text
                            warmup_body = warmup.json()
                            active_builder_call = (
                                diagnosis_builder.call_args
                                if view_kind == "diagnosis"
                                else maintenance_builder.call_args
                            )
                            assert len(warmup_body["data"]) == expected_rows, (
                                name,
                                warmup_body["meta"],
                                active_builder_call,
                            )

                            end_to_end_samples: list[float] = []
                            database_samples: list[float] = []
                            application_samples: list[float] = []
                            query_counts: list[int] = []
                            response_sizes: list[int] = []
                            timed_statement_samples: list[tuple[str, float]] = []
                            last_response = warmup
                            for _iteration in range(PERFORMANCE_SAMPLE_COUNT):
                                reset_sql_metrics()
                                started = perf_counter()
                                last_response = await client.get(
                                    path,
                                    params=parameters,
                                    headers=scope_headers,
                                )
                                elapsed_ms = (perf_counter() - started) * 1_000
                                assert last_response.status_code == 200, last_response.text
                                database_ms = float(sql_metrics["milliseconds"])
                                end_to_end_samples.append(elapsed_ms)
                                database_samples.append(database_ms)
                                application_samples.append(max(0.0, elapsed_ms - database_ms))
                                query_counts.append(int(sql_metrics["count"]))
                                response_sizes.append(len(last_response.content))
                                timed_statement_samples.extend(statement_samples)

                            gc.collect()
                            tracemalloc.start()
                            try:
                                reset_sql_metrics()
                                memory_response = await client.get(
                                    path,
                                    params=parameters,
                                    headers=scope_headers,
                                )
                                _, python_peak_bytes = tracemalloc.get_traced_memory()
                            finally:
                                tracemalloc.stop()
                            assert memory_response.status_code == 200, memory_response.text

                            body = last_response.json()
                            assert len(body["data"]) == expected_rows, (
                                name,
                                body["meta"],
                            )
                            boundaries = body["meta"]["related_data_boundaries"]
                            if view_kind == "diagnosis":
                                assert all(
                                    len(row["citations"]) == DIAGNOSIS_EVIDENCE_PER_MISSION_LIMIT
                                    for row in body["data"]
                                )
                                assert all(
                                    len(row["collaboration"])
                                    == DIAGNOSIS_EXECUTIONS_PER_MISSION_LIMIT
                                    for row in body["data"]
                                )
                                assert boundaries["evidence"]["truncated_mission_count"] == (
                                    expected_rows
                                )
                                assert (
                                    boundaries["agent_executions"]["truncated_mission_count"]
                                    == expected_rows
                                )
                            else:
                                assert boundaries["tasks"]["strategy"] == "aggregate_only"
                                assert (
                                    boundaries["reservations"]["per_mission_type_limit"]
                                    == MAINTENANCE_RESOURCES_PER_MISSION_TYPE_LIMIT
                                )
                                assert boundaries["reservations"]["truncated_group_count"] == (
                                    expected_rows * 4
                                )
                                assert (
                                    boundaries["weather_windows"]["per_work_order_limit"]
                                    == MAINTENANCE_WEATHER_PER_WORK_ORDER_LIMIT
                                )
                                assert (
                                    boundaries["weather_windows"]["truncated_work_order_count"]
                                    == expected_rows
                                )
                                assert all(
                                    row["weather"]["state"] == "unsafe" for row in body["data"]
                                )
                                assert all(
                                    len(row[resource_key])
                                    <= MAINTENANCE_RESOURCES_PER_MISSION_TYPE_LIMIT
                                    for row in body["data"]
                                    for resource_key in ("vessels", "spareParts", "tools")
                                )

                            e2e_p95_ms = _percentile(end_to_end_samples, 0.95)
                            e2e_p99_ms = _percentile(end_to_end_samples, 0.99)
                            db_p95_ms = _percentile(database_samples, 0.95)
                            db_p99_ms = _percentile(database_samples, 0.99)
                            application_p95_ms = _percentile(application_samples, 0.95)
                            application_p99_ms = _percentile(application_samples, 0.99)
                            response_bytes = max(response_sizes)
                            record_testsuite_property(f"{name}_sql_count_max", max(query_counts))
                            record_testsuite_property(
                                f"{name}_database_p95_ms", round(db_p95_ms, 3)
                            )
                            record_testsuite_property(
                                f"{name}_database_p99_ms", round(db_p99_ms, 3)
                            )
                            record_testsuite_property(
                                f"{name}_application_p95_ms", round(application_p95_ms, 3)
                            )
                            record_testsuite_property(
                                f"{name}_application_p99_ms", round(application_p99_ms, 3)
                            )
                            record_testsuite_property(
                                f"{name}_end_to_end_p95_ms", round(e2e_p95_ms, 3)
                            )
                            record_testsuite_property(
                                f"{name}_end_to_end_p99_ms", round(e2e_p99_ms, 3)
                            )
                            record_testsuite_property(
                                f"{name}_end_to_end_max_ms",
                                round(max(end_to_end_samples), 3),
                            )
                            record_testsuite_property(
                                f"{name}_database_max_ms",
                                round(max(database_samples), 3),
                            )
                            record_testsuite_property(
                                f"{name}_python_peak_bytes", python_peak_bytes
                            )
                            record_testsuite_property(f"{name}_response_bytes", response_bytes)
                            slowest_label, slowest_sql_ms = max(
                                timed_statement_samples,
                                key=lambda sample: sample[1],
                            )
                            record_testsuite_property(f"{name}_slowest_sql", slowest_label)
                            record_testsuite_property(
                                f"{name}_slowest_sql_ms",
                                round(slowest_sql_ms, 3),
                            )
                            assert len(set(query_counts)) == 1
                            assert max(query_counts) <= query_budget
                            assert db_p95_ms <= e2e_p95_ms
                            assert e2e_p95_ms < 500
                            assert e2e_p99_ms < 1_000
                            assert python_peak_bytes < 64 * 1024 * 1024
                            if name == "work_order_weather_limit_one":
                                assert python_peak_bytes < 8 * 1024 * 1024
                            assert 1_000 < response_bytes < 512 * 1024

                        calls_per_scenario = PERFORMANCE_SAMPLE_COUNT + 2
                        assert diagnosis_builder.call_count == calls_per_scenario * 2
                        assert maintenance_builder.call_count == calls_per_scenario * 3

                        deterministic_fallback = await client.get(
                            "/api/v1/maintenance-plans",
                            params={"sort": "start-asc", "offset": 0, "limit": 1},
                            headers=scoped_headers,
                        )
                        assert deterministic_fallback.status_code == 200
                        assert (
                            deterministic_fallback.json()["data"][0]["weather"]["id"]
                            == "PERF-WEATHER-0000000001"
                        )

                        async with engine.begin() as connection:
                            await connection.execute(
                                text(
                                    "INSERT INTO tenants (id, name) VALUES "
                                    "('tenant-other', 'Other weather contract tenant')"
                                )
                            )
                            await connection.execute(
                                text(
                                    "INSERT INTO wind_farms "
                                    "(id, tenant_id, name, capacity_mw) VALUES "
                                    "('WF-PERF-OTHER', 'tenant-other', "
                                    "'Cross-farm weather contract', 1.0)"
                                )
                            )
                            await connection.execute(
                                text(
                                    "INSERT INTO weather_windows "
                                    "(id, wind_farm_id, starts_at, ends_at, wind_speed_ms, "
                                    "wave_height_m, suitable, attributes) VALUES "
                                    "('PERF-WEATHER-SUITABLE-B', 'WF-PERF', "
                                    "now() - interval '30 minutes', now() + interval '25 days', "
                                    "8.0, 1.0, true, '{}'::jsonb), "
                                    "('PERF-WEATHER-SUITABLE-A', 'WF-PERF', "
                                    "now() - interval '30 minutes', now() + interval '20 days', "
                                    "7.0, 1.0, true, '{}'::jsonb), "
                                    "('PERF-WEATHER-CROSS-FARM', 'WF-PERF-OTHER', "
                                    "now() - interval '2 hours', now() + interval '30 days', "
                                    "5.0, 0.5, true, '{}'::jsonb)"
                                )
                            )

                        suitable_first = await client.get(
                            "/api/v1/maintenance-plans",
                            params={"sort": "start-asc", "offset": 0, "limit": 1},
                            headers=scoped_headers,
                        )
                        assert suitable_first.status_code == 200
                        suitable_body = suitable_first.json()
                        assert (
                            suitable_body["data"][0]["weather"]["id"] == "PERF-WEATHER-SUITABLE-A"
                        )
                        assert suitable_body["data"][0]["weather"]["state"] == "suitable"
                        assert (
                            suitable_body["meta"]["related_data_boundaries"]["weather_windows"][
                                "truncated_work_order_count"
                            ]
                            == 1
                        )

                        wrong_tenant = await client.get(
                            "/api/v1/maintenance-plans",
                            params={"sort": "start-asc", "offset": 0, "limit": 1},
                            headers={"X-WindOps-Test-Tenant-Ids": "tenant-other"},
                        )
                        assert wrong_tenant.status_code == 200
                        assert wrong_tenant.json()["data"] == []

                        async with engine.begin() as connection:
                            await connection.execute(
                                text("DELETE FROM weather_windows WHERE wind_farm_id = 'WF-PERF'")
                            )
                        unmatched = await client.get(
                            "/api/v1/maintenance-plans",
                            params={"sort": "start-asc", "offset": 0, "limit": 1},
                            headers=scoped_headers,
                        )
                        assert unmatched.status_code == 200
                        unmatched_body = unmatched.json()
                        assert unmatched_body["data"][0]["weather"]["id"] is None
                        assert unmatched_body["data"][0]["weather"]["state"] == "unmatched"
                        assert (
                            unmatched_body["meta"]["related_data_boundaries"]["weather_windows"][
                                "truncated_work_order_count"
                            ]
                            == 0
                        )
            finally:
                event.remove(sync_engine, "before_cursor_execute", before_cursor_execute)
                event.remove(sync_engine, "after_cursor_execute", after_cursor_execute)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_real_production_rotation_contract_uses_fastapi_and_postgresql(
    migration_database_urls: tuple[str, str],
) -> None:
    """Exercise pending-readiness, delegated confirmation, and recovery on real PostgreSQL."""

    database_url, _ = migration_database_urls
    _run_alembic(database_url, "upgrade", "head")
    settings = Settings(
        environment=Environment.TEST,
        database_url=database_url,
        schema_bootstrap=False,
        demo_seed=False,
        knowledge_graph_backend="memory",
        outbox_inline_drain=True,
        auth_mode="sites_delegation",
        gateway_delegation_secret=DELEGATION_SECRET,
        identity_role_mappings={"sites-release-manager": ["operations_manager"]},
        identity_scope_mappings={
            "sites-release-manager": IdentityAccessScope(
                data_scopes=["platform"],
                allow_global=True,
            )
        },
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with app.state.session_factory() as session, session.begin():
            revision_id = "external-rotation-revision"
            audit_id = "external-rotation-audit"
            session.add(
                PlatformConfigurationRevision(
                    id=revision_id,
                    configuration_key="backup_policy",
                    revision=1,
                    value={},
                    secret_reference=None,
                    security_status="quarantined_rotation_required",
                    active=False,
                    reason="external rotation contract fixture",
                    created_by="external-test",
                )
            )
            session.add(
                PlatformConfigurationSecurityAudit(
                    id=audit_id,
                    configuration_id=revision_id,
                    configuration_key="backup_policy",
                    revision=1,
                    finding_categories=["invalid_secret_reference"],
                    original_fingerprint="a" * 64,
                    action="quarantined_and_redacted",
                    rotation_required=True,
                )
            )

        class FakeRedis:
            async def ping(self) -> bool:
                return True

            async def aclose(self) -> None:
                return None

        class FakeMinio:
            def bucket_exists(self, _bucket: str) -> bool:
                return True

        # Keep graph/Redis/object-store doubles narrow while the API, auth,
        # migration schema, rotation audit, and readiness query use PostgreSQL.
        app.state.settings.environment = Environment.PRODUCTION
        app.state.settings.release_id = "external-rotation-release"
        app.state.settings.release_commit_sha = "a" * 40
        app.state.settings.release_image_digest = "sha256:" + "b" * 64
        app.state.redis_client = FakeRedis()
        app.state.minio_client = FakeMinio()

        def token(
            *,
            method: str,
            target: str,
            body: bytes,
            jti: str,
            subject: str = "sites-release-manager",
        ) -> str:
            now = datetime.now(UTC)
            return jwt.encode(
                {
                    "iss": "windops-sites-gateway",
                    "aud": "windops-python-backend",
                    "sub": subject,
                    "email": "release-manager@example.com",
                    "iat": now,
                    "exp": now + timedelta(seconds=60),
                    "jti": jti,
                    "method": method,
                    "target": target,
                    "body_sha256": hashlib.sha256(body).hexdigest(),
                },
                DELEGATION_SECRET,
                algorithm="HS256",
            )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            not_ready = await client.get("/api/v1/readyz")
            assert not_ready.status_code == 503
            assert "CONFIGURATION_SECURITY_REMEDIATION_REQUIRED" in not_ready.text

            body = (
                b'{"replacement_secret_reference":"vault://windops/platform/rotated",'
                b'"rotation_evidence":"CHG-EXTERNAL-ROTATION-001"}'
            )
            target = (
                f"/api/v1/platform/configuration-security-audits/{audit_id}/rotation-confirmation"
            )
            confirmed = await client.post(
                target,
                content=body,
                headers={
                    "Authorization": "Bearer "
                    + token(method="POST", target=target, body=body, jti="external-rotation-jti"),
                    "Content-Type": "application/json",
                    "Idempotency-Key": "external-rotation-confirm-001",
                },
            )
            assert confirmed.status_code == 200, confirmed.text
            assert confirmed.json()["rotation_required"] is False

            ready = await client.get("/api/v1/readyz")
            assert ready.status_code == 200, ready.text
            assert ready.json()["status"] == "ready"

            replay = await client.post(
                target,
                content=body,
                headers={
                    "Authorization": "Bearer "
                    + token(method="POST", target=target, body=body, jti="external-rotation-jti"),
                    "Content-Type": "application/json",
                    "Idempotency-Key": "external-rotation-confirm-002",
                },
            )
            assert replay.status_code == 401
            assert replay.json()["error"]["code"] == "DELEGATED_IDENTITY_REPLAYED"

            unauthorized_body = body
            unauthorized = await client.post(
                target,
                content=unauthorized_body,
                headers={
                    "Authorization": "Bearer "
                    + token(
                        method="POST",
                        target=target,
                        body=unauthorized_body,
                        jti="external-rotation-unauthorized",
                        subject="unassigned-sites-user",
                    ),
                    "Content-Type": "application/json",
                    "Idempotency-Key": "external-rotation-confirm-003",
                },
            )
            assert unauthorized.status_code == 403


async def _verify_previous_supported_upgrade(
    database_url: str,
    controlled_secret: str,
) -> None:
    _run_alembic(database_url, "upgrade", "0017_knowledge_document_access_scope")
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("CREATE TABLE platform_configuration_security_audits (sentinel INTEGER)")
            )
    finally:
        await engine.dispose()

    failed = _run_alembic(database_url, "upgrade", "head", check=False)
    assert failed.returncode != 0
    current_after_failure = _run_alembic(database_url, "current")
    assert "0017_knowledge_document_access_scope" in current_after_failure.stdout

    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            new_columns = int(
                await connection.scalar(
                    text(
                        "SELECT count(*) FROM information_schema.columns "
                        "WHERE table_name = 'platform_configuration_revisions' "
                        "AND column_name IN ('schema_version', 'security_status')"
                    )
                )
                or 0
            )
            assert new_columns == 0
        async with engine.begin() as connection:
            await connection.execute(text("DROP TABLE platform_configuration_security_audits"))
    finally:
        await engine.dispose()

    _run_alembic(database_url, "upgrade", "head")
    current = _run_alembic(database_url, "current")
    assert HEAD_REVISION in current.stdout
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            farm = (
                await connection.execute(
                    text("SELECT name, tenant_id FROM wind_farms WHERE id = 'WF-UPGRADE'")
                )
            ).one()
            assert farm == ("Upgrade compatibility farm", "tenant-east-china")
            document = (
                await connection.execute(
                    text(
                        "SELECT body, tenant_id, data_scope FROM knowledge_documents "
                        "WHERE id = 'KB-UPGRADE'"
                    )
                )
            ).one()
            assert document == (
                "Representative retained content",
                "tenant-east-china",
                "knowledge",
            )
            configuration = (
                await connection.execute(
                    text(
                        "SELECT value, active, schema_version, security_status, reason "
                        "FROM platform_configuration_revisions "
                        "WHERE id = 'CFG-UPGRADE-SECRET'"
                    )
                )
            ).one()
            assert configuration.value == {}
            assert configuration.active is False
            assert configuration.schema_version == 1
            assert configuration.security_status == "quarantined_rotation_required"
            assert controlled_secret not in configuration.reason
            audit = (
                await connection.execute(
                    text(
                        "SELECT action, rotation_required, finding_categories::text "
                        "FROM platform_configuration_security_audits "
                        "WHERE configuration_id = 'CFG-UPGRADE-SECRET'"
                    )
                )
            ).one()
            assert audit.action == "quarantined_and_redacted"
            assert audit.rotation_required is True
            assert controlled_secret not in audit.finding_categories
            residual = int(
                await connection.scalar(
                    text(
                        "SELECT count(*) FROM platform_configuration_revisions "
                        "WHERE value::text LIKE :marker OR reason LIKE :marker "
                        "OR COALESCE(secret_reference, '') LIKE :marker"
                    ),
                    {"marker": f"%{controlled_secret}%"},
                )
                or 0
            )
            assert residual == 0
    finally:
        await engine.dispose()
