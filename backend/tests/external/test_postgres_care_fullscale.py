from __future__ import annotations

import json
import math
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import event, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

from windops_backend.benchmarks.care.fullscale import (
    register_full_scale_evaluation,
    register_full_scale_import,
)
from windops_backend.config import Settings
from windops_backend.enums import Environment
from windops_backend.main import create_app
from windops_backend.models import (
    BenchmarkDatasetVersion,
    BenchmarkEvaluationRun,
    BenchmarkEvent,
    BenchmarkEventResult,
    BenchmarkFeatureMap,
    BenchmarkFile,
    BenchmarkMetricSnapshot,
    BenchmarkQualityReport,
    RegisteredModel,
    ScadaSample,
)

pytestmark = [
    pytest.mark.external_release,
    pytest.mark.skipif(
        os.getenv("WINDOPS_RUN_POSTGRES_CONTRACT_TESTS") != "1",
        reason="requires an isolated migrated PostgreSQL database",
    ),
]

TENANT_ID = "tenant-east-china"
SUBJECT = "care-full-scale-integration"
MAX_RESPONSE_BYTES = 512 * 1024
MAX_QUERY_P95_SECONDS = 0.5
MAX_QUERY_SQL_STATEMENTS = 12


@dataclass
class _SqlProfile:
    statement_count: int = 0
    elapsed_seconds: float = 0.0


@contextmanager
def _capture_sql_profile(engine: AsyncEngine) -> Iterator[_SqlProfile]:
    profile = _SqlProfile()

    def before_cursor_execute(
        _connection: Any,
        _cursor: Any,
        _statement: Any,
        _parameters: Any,
        context: Any,
        _executemany: Any,
    ) -> None:
        context._windops_profile_started = time.perf_counter()

    def after_cursor_execute(
        _connection: Any,
        _cursor: Any,
        _statement: Any,
        _parameters: Any,
        context: Any,
        _executemany: Any,
    ) -> None:
        profile.statement_count += 1
        profile.elapsed_seconds += time.perf_counter() - context._windops_profile_started

    sync_engine = engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", before_cursor_execute)
    event.listen(sync_engine, "after_cursor_execute", after_cursor_execute)
    try:
        yield profile
    finally:
        event.remove(sync_engine, "before_cursor_execute", before_cursor_execute)
        event.remove(sync_engine, "after_cursor_execute", after_cursor_execute)


def _database_url() -> str:
    value = os.getenv("WINDOPS_POSTGRES_TEST_URL", "").strip()
    if value.startswith("postgres://"):
        value = "postgresql+asyncpg://" + value.removeprefix("postgres://")
    elif value.startswith("postgresql://"):
        value = "postgresql+asyncpg://" + value.removeprefix("postgresql://")
    if not value:
        raise RuntimeError("WINDOPS_POSTGRES_TEST_URL is required")
    return make_url(value).render_as_string(hide_password=False)


def _artifact_roots() -> tuple[Path, Path]:
    base_value = os.getenv("WINDOPS_CARE_REAL_ARTIFACT_ROOT", "").strip()
    full_value = os.getenv("WINDOPS_CARE_FULL_SCALE_ROOT", "").strip()
    if not base_value or not full_value:
        raise RuntimeError(
            "WINDOPS_CARE_REAL_ARTIFACT_ROOT and WINDOPS_CARE_FULL_SCALE_ROOT are required"
        )
    return Path(base_value).resolve(strict=True), Path(full_value).resolve(strict=True)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"{path} is not a JSON object")
    return value


def _headers(*scopes: str) -> dict[str, str]:
    return {
        "X-WindOps-Test-Principal": SUBJECT,
        "X-WindOps-Test-Role": "operations_manager",
        "X-WindOps-Test-Tenant-Ids": TENANT_ID,
        "X-WindOps-Test-Data-Scopes": ",".join(scopes),
    }


@pytest.mark.asyncio
async def test_real_postgres_full_scale_registration_catalog_and_query_budget(
    record_testsuite_property: Any,
) -> None:
    base_root, full_root = _artifact_roots()
    source_manifest = _read_json(base_root / "contract/manifest.json")
    quality_contract = _read_json(base_root / "quality/quality-contract.json")
    import_manifest = _read_json(full_root / "care/v6/reports/full-import/manifest.json")
    evaluation_manifest = _read_json(full_root / "care/v6/reports/full-evaluation/manifest.json")
    metric_count = sum(
        5
        + sum(
            summary.get(name) is not None
            for name in (
                "care_score",
                "normal_event_false_positive_rate",
                "event_detection_rate",
            )
        )
        for summary in evaluation_manifest["fold_summaries"]
    )
    expected_evaluation_records = 3 + 36 + 95 + metric_count

    settings = Settings(
        environment=Environment.TEST,
        database_url=_database_url(),
        schema_bootstrap=False,
        demo_seed=True,
        test_auth_bypass_enabled=True,
        knowledge_graph_backend="memory",
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with app.state.session_factory() as session, session.begin():
            imported_first = await register_full_scale_import(
                session,
                import_manifest,
                source_manifest,
                quality_contract,
                artifact_root=full_root,
                tenant_id=TENANT_ID,
                subject=SUBJECT,
            )
            evaluated_first = await register_full_scale_evaluation(
                session,
                evaluation_manifest,
                import_manifest,
                artifact_root=full_root,
                subject=SUBJECT,
            )
        assert (imported_first.created_count, imported_first.replayed_count) in {
            (1571, 0),
            (0, 1571),
        }
        assert (evaluated_first.created_count, evaluated_first.replayed_count) in {
            (expected_evaluation_records, 0),
            (0, expected_evaluation_records),
        }

        async with app.state.session_factory() as session, session.begin():
            imported_replay = await register_full_scale_import(
                session,
                import_manifest,
                source_manifest,
                quality_contract,
                artifact_root=full_root,
                tenant_id=TENANT_ID,
                subject=SUBJECT,
            )
            evaluated_replay = await register_full_scale_evaluation(
                session,
                evaluation_manifest,
                import_manifest,
                artifact_root=full_root,
                subject=SUBJECT,
            )
        assert imported_replay.created_count == 0
        assert imported_replay.replayed_count == 1571
        assert evaluated_replay.created_count == 0
        assert evaluated_replay.replayed_count == expected_evaluation_records

        async with app.state.session_factory() as session:
            expected_counts = {
                BenchmarkDatasetVersion: 1,
                BenchmarkFile: 95,
                BenchmarkEvent: 95,
                BenchmarkFeatureMap: 1285,
                BenchmarkQualityReport: 95,
                RegisteredModel: 3,
                BenchmarkEvaluationRun: 36,
                BenchmarkEventResult: 95,
                BenchmarkMetricSnapshot: metric_count,
            }
            for model, count in expected_counts.items():
                actual = int(await session.scalar(select(func.count()).select_from(model)) or 0)
                assert actual == count, model.__tablename__
            events = list((await session.scalars(select(BenchmarkEvent))).all())
            assert len({(event.farm, event.source_asset_id) for event in events}) == 36
            assert sum(event.event_label == "anomaly" for event in events) == 45
            assert sum(event.event_label == "normal" for event in events) == 50
            assert sum(event.train_row_count + event.prediction_row_count for event in events) == (
                5_242_948
            )
            assert (
                int(
                    await session.scalar(
                        select(func.count())
                        .select_from(ScadaSample)
                        .where(ScadaSample.source_id == "care-v6-replay")
                    )
                    or 0
                )
                == 0
            )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            benchmark_headers = _headers("benchmark", "model")
            evaluation_paths = (
                "/api/v1/benchmarks/evaluations?limit=32&offset=0",
                "/api/v1/benchmarks/evaluations?limit=32&offset=32",
            )
            paths = (
                "/api/v1/benchmarks/datasets?limit=10",
                "/api/v1/benchmarks/datasets/care-v6/events?limit=64&offset=0",
                "/api/v1/benchmarks/datasets/care-v6/events?limit=64&offset=64",
                *evaluation_paths,
            )
            for path in paths:
                warm = await client.get(path, headers=benchmark_headers)
                assert warm.status_code == 200, warm.text
                assert len(warm.content) <= MAX_RESPONSE_BYTES

            timings_by_path: dict[str, list[float]] = {path: [] for path in paths}
            sql_counts_by_path: dict[str, list[int]] = {path: [] for path in paths}
            sql_timings_by_path: dict[str, list[float]] = {path: [] for path in paths}
            responses: dict[str, httpx.Response] = {}
            max_response_bytes = 0
            for _ in range(20):
                for path in paths:
                    with _capture_sql_profile(app.state.engine) as sql_profile:
                        started = time.perf_counter()
                        response = await client.get(path, headers=benchmark_headers)
                    timings_by_path[path].append(time.perf_counter() - started)
                    sql_counts_by_path[path].append(sql_profile.statement_count)
                    sql_timings_by_path[path].append(sql_profile.elapsed_seconds)
                    assert response.status_code == 200, response.text
                    assert len(response.content) <= MAX_RESPONSE_BYTES
                    max_response_bytes = max(max_response_bytes, len(response.content))
                    responses[path] = response
            p95_by_path = {
                path: sorted(timings)[math.ceil(len(timings) * 0.95) - 1]
                for path, timings in timings_by_path.items()
            }
            p95_seconds = max(p95_by_path.values())
            sql_p95_by_path = {
                path: sorted(timings)[math.ceil(len(timings) * 0.95) - 1]
                for path, timings in sql_timings_by_path.items()
            }
            for index, path in enumerate(paths):
                record_testsuite_property(
                    f"care.full_scale.query_{index}_p95_ms",
                    f"{p95_by_path[path] * 1000:.3f}",
                )
                record_testsuite_property(f"care.full_scale.query_{index}_path", path)
                record_testsuite_property(
                    f"care.full_scale.query_{index}_sql_count_max",
                    str(max(sql_counts_by_path[path])),
                )
                record_testsuite_property(
                    f"care.full_scale.query_{index}_sql_p95_ms",
                    f"{sql_p95_by_path[path] * 1000:.3f}",
                )
            record_testsuite_property("care.full_scale.query_p95_ms", f"{p95_seconds * 1000:.3f}")
            record_testsuite_property(
                "care.full_scale.query_sql_count_max",
                str(max(max(counts) for counts in sql_counts_by_path.values())),
            )
            record_testsuite_property(
                "care.full_scale.query_sql_p95_ms",
                f"{max(sql_p95_by_path.values()) * 1000:.3f}",
            )
            record_testsuite_property(
                "care.full_scale.measured_max_response_bytes", str(max_response_bytes)
            )
            assert all(
                max(counts) <= MAX_QUERY_SQL_STATEMENTS for counts in sql_counts_by_path.values()
            )
            assert p95_seconds <= MAX_QUERY_P95_SECONDS

            dataset = responses[paths[0]].json()["data"][0]
            assert dataset["coverage"]["registered_event_count"] == 95
            assert dataset["coverage"]["asset_count"] == 36
            assert dataset["coverage"]["time_point_count"] == 5_242_948
            assert dataset["mapping"]["total"] == 1285
            assert dataset["mapping"]["enabled"] == 355
            assert dataset["runs"]["evaluation"]["completed"] == 36
            assert dataset["runs"]["replay"] == {}

            first_events = responses[paths[1]].json()
            second_events = responses[paths[2]].json()
            assert len(first_events["data"]) == 64
            assert len(second_events["data"]) == 31
            assert first_events["meta"]["filtered_total"] == 95
            assert second_events["meta"]["filtered_total"] == 95
            assert all(
                event["truth"]["event_label"] is None
                for event in [*first_events["data"], *second_events["data"]]
            )

            evaluation_pages = [responses[path].json() for path in evaluation_paths]
            assert all(page["meta"]["filtered_total"] == 36 for page in evaluation_pages)
            evaluation_rows = [row for page in evaluation_pages for row in page["data"]]
            assert len(evaluation_rows) == 36
            assert sum(row["event_accounting"]["requested"] for row in evaluation_rows) == 95
            assert all(
                row["event_accounting"]["failed"] == 0
                and row["event_accounting"]["unscorable"] == 0
                and row["run"]["prediction_truth_used"] is False
                for row in evaluation_rows
            )

            truth = await client.get(
                "/api/v1/benchmarks/datasets/care-v6/events?limit=64&revealTruth=true",
                headers=_headers("benchmark", "model", "benchmark_truth"),
            )
            assert truth.status_code == 200, truth.text
            truth_second = await client.get(
                "/api/v1/benchmarks/datasets/care-v6/events?limit=64&offset=64&revealTruth=true",
                headers=_headers("benchmark", "model", "benchmark_truth"),
            )
            assert truth_second.status_code == 200, truth_second.text
            assert (
                sum(row["truth"]["event_label"] == "anomaly" for row in truth.json()["data"])
                + sum(
                    row["truth"]["event_label"] == "anomaly" for row in truth_second.json()["data"]
                )
                == 45
            )
            denied = await client.get(
                "/api/v1/benchmarks/datasets",
                headers=_headers("platform"),
            )
            assert denied.status_code == 403

    record_testsuite_property("care.full_scale.import_created", str(imported_first.created_count))
    record_testsuite_property(
        "care.full_scale.evaluation_created", str(evaluated_first.created_count)
    )
    record_testsuite_property("care.full_scale.metric_count", str(metric_count))
    record_testsuite_property("care.full_scale.max_response_bytes", str(MAX_RESPONSE_BYTES))
    record_testsuite_property("care.full_scale.timescale_signal_rows", "0")
    record_testsuite_property(
        "care.full_scale.source_manifest_sha256", source_manifest["manifest_sha256"]
    )
    record_testsuite_property(
        "care.full_scale.quality_contract_sha256",
        quality_contract["quality_contract_sha256"],
    )
    record_testsuite_property(
        "care.full_scale.import_manifest_sha256", import_manifest["manifest_sha256"]
    )
    record_testsuite_property(
        "care.full_scale.evaluation_manifest_sha256",
        evaluation_manifest["manifest_sha256"],
    )
    record_testsuite_property(
        "care.full_scale.approved_root_sha256",
        evaluation_manifest["care_approval"]["approved_root_sha256"],
    )
