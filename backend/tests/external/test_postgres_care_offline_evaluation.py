from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from test_care_evaluation import CREATED_AT
from test_care_importer import _build as build_minimal_import_fixture
from windops_backend.benchmarks.care.evaluation import (
    build_offline_evaluations,
    register_offline_evaluations,
)
from windops_backend.benchmarks.care.importer import register_a_minimal_import
from windops_backend.models import (
    BenchmarkEvaluationRun,
    BenchmarkEventResult,
    BenchmarkMetricSnapshot,
    RegisteredModel,
)

pytestmark = [
    pytest.mark.external_release,
    pytest.mark.skipif(
        os.getenv("WINDOPS_RUN_POSTGRES_CONTRACT_TESTS") != "1",
        reason="requires an isolated migrated PostgreSQL database",
    ),
]


def _database_url() -> str:
    value = os.getenv("WINDOPS_POSTGRES_TEST_URL", "").strip()
    if value.startswith("postgres://"):
        value = "postgresql+asyncpg://" + value.removeprefix("postgres://")
    elif value.startswith("postgresql://"):
        value = "postgresql+asyncpg://" + value.removeprefix("postgresql://")
    if not value:
        raise RuntimeError("WINDOPS_POSTGRES_TEST_URL is required")
    return make_url(value).render_as_string(hide_password=False)


def _load_real_documents(
    root_value: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], Path]:
    root = Path(root_value).resolve(strict=True)

    def load(relative: str) -> dict[str, Any]:
        value = json.loads((root / relative).read_text(encoding="utf-8"))
        assert isinstance(value, dict)
        return value

    return (
        load("contract/manifest.json"),
        load("quality/quality-contract.json"),
        load("minimal-import/care/v6/reports/a-minimal-import/manifest.json"),
        load("offline-evaluation/care/v6/reports/offline-evaluation/manifest.json"),
        root / "offline-evaluation",
    )


@pytest.mark.asyncio
async def test_postgres_offline_evaluation_registration_is_exactly_idempotent(
    tmp_path: Path,
    record_testsuite_property: Any,
) -> None:
    real_root_value = os.getenv("WINDOPS_CARE_REAL_ARTIFACT_ROOT", "").strip()
    trust_anchor = None
    if real_root_value:
        source_manifest, quality, imported_manifest, evaluated_manifest, evaluation_root = (
            _load_real_documents(real_root_value)
        )
    else:
        (
            _,
            _,
            source_manifest,
            quality,
            import_root,
            _,
            imported,
            trust_anchor,
        ) = build_minimal_import_fixture(tmp_path)
        imported_manifest = imported.manifest
        evaluated_manifest = build_offline_evaluations(
            imported_manifest,
            quality,
            import_root,
            tmp_path / "evaluation-output",
            created_at=CREATED_AT,
            trust_anchor=trust_anchor,
        ).manifest
        evaluation_root = tmp_path / "evaluation-output"
    engine = create_async_engine(_database_url(), pool_size=2, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session, session.begin():
            imported_registration = await register_a_minimal_import(
                session,
                imported_manifest,
                source_manifest,
                quality,
                tenant_id="tenant-east-china",
                subject="care-worker",
                trust_anchor=trust_anchor,
            )
            first = await register_offline_evaluations(
                session,
                evaluated_manifest,
                artifact_root=evaluation_root,
                subject="care-worker",
                trust_anchor=trust_anchor,
            )
        assert imported_registration.created_count == 88
        expected = sum(2 + 2 + len(model["metrics"]) for model in evaluated_manifest["models"])
        assert first.created_count == expected
        assert first.replayed_count == 0

        async with factory() as session, session.begin():
            imported_replay = await register_a_minimal_import(
                session,
                imported_manifest,
                source_manifest,
                quality,
                tenant_id="tenant-east-china",
                subject="care-worker",
                trust_anchor=trust_anchor,
            )
            replay = await register_offline_evaluations(
                session,
                evaluated_manifest,
                artifact_root=evaluation_root,
                subject="care-worker",
                trust_anchor=trust_anchor,
            )
        assert imported_replay.created_count == 0
        assert imported_replay.replayed_count == 88
        assert replay.created_count == 0
        assert replay.replayed_count == expected

        async with factory() as session:
            assert (
                int(
                    await session.scalar(
                        select(func.count(RegisteredModel.id)).where(
                            RegisteredModel.id.in_(first.model_ids)
                        )
                    )
                    or 0
                )
                == 2
            )
            assert (
                int(
                    await session.scalar(
                        select(func.count(BenchmarkEvaluationRun.id)).where(
                            BenchmarkEvaluationRun.id.in_(first.evaluation_run_ids),
                            BenchmarkEvaluationRun.status == "completed",
                        )
                    )
                    or 0
                )
                == 2
            )
            assert (
                int(
                    await session.scalar(
                        select(func.count(BenchmarkEventResult.id)).where(
                            BenchmarkEventResult.evaluation_run_id.in_(first.evaluation_run_ids)
                        )
                    )
                    or 0
                )
                == 4
            )
            assert int(
                await session.scalar(
                    select(func.count(BenchmarkMetricSnapshot.id)).where(
                        BenchmarkMetricSnapshot.evaluation_run_id.in_(first.evaluation_run_ids)
                    )
                )
                or 0
            ) == sum(len(model["metrics"]) for model in evaluated_manifest["models"])
    finally:
        await engine.dispose()
    record_testsuite_property(
        "care.offline.source_manifest_sha256", source_manifest["manifest_sha256"]
    )
    record_testsuite_property(
        "care.offline.quality_contract_sha256", quality["quality_contract_sha256"]
    )
    record_testsuite_property(
        "care.offline.import_identity_sha256",
        imported_manifest["immutable_registration_identity"],
    )
    record_testsuite_property(
        "care.offline.evaluation_identity_sha256",
        evaluated_manifest["evaluation_identity_sha256"],
    )
    record_testsuite_property(
        "care.offline.approved_root_sha256",
        evaluated_manifest["care_approval"]["approved_root_sha256"],
    )
