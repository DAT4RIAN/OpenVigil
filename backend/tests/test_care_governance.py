from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import pytest
from fastapi import FastAPI
from sqlalchemy import select

from windops_backend.benchmarks.care.pipeline import CareObjectStorageLayout
from windops_backend.models import DomainEvent
from windops_backend.services.benchmark_governance import (
    BenchmarkArtifactCleanupError,
    BenchmarkArtifactScopeError,
    CareArtifactCleanupScope,
    execute_care_artifact_cleanup,
)

DATASET_SHA256 = "a" * 64
OBJECT_SHA256 = "b" * 64


@dataclass(frozen=True, slots=True)
class _ListedObject:
    object_name: str


@dataclass(frozen=True, slots=True)
class _StoredObject:
    metadata: dict[str, str]


class _CleanupClient:
    def __init__(self, objects: dict[str, str], *, fail_on: str | None = None) -> None:
        self.objects = dict(objects)
        self.fail_on = fail_on
        self.list_calls: list[tuple[str, str, bool]] = []
        self.removed: list[str] = []

    def list_objects(self, bucket: str, *, prefix: str, recursive: bool) -> list[_ListedObject]:
        self.list_calls.append((bucket, prefix, recursive))
        return [_ListedObject(key) for key in self.objects if key.startswith(prefix)]

    def stat_object(self, bucket: str, object_name: str) -> _StoredObject:
        del bucket
        return _StoredObject({"x-amz-meta-sha256": self.objects[object_name]})

    def remove_object(self, bucket: str, object_name: str) -> None:
        del bucket
        if object_name == self.fail_on:
            raise RuntimeError("fixture object-store failure")
        self.removed.append(object_name)


def _event_scope() -> CareArtifactCleanupScope:
    return CareArtifactCleanupScope(
        dataset_id="care",
        dataset_version="v6",
        dataset_sha256=DATASET_SHA256,
        layer="standard",
        farm="A",
        event_id=0,
    )


@pytest.mark.asyncio
async def test_care_cleanup_requires_exact_confirmed_scope_and_content_set(
    app: FastAPI,
) -> None:
    layout = CareObjectStorageLayout()
    scope = _event_scope()
    prefix = scope.object_prefix(layout)
    objects = {
        f"{prefix}/data.sha256-{OBJECT_SHA256}.parquet": OBJECT_SHA256,
        f"{prefix}/manifest.sha256-{DATASET_SHA256}.json": DATASET_SHA256,
    }
    client = _CleanupClient(objects)
    async with app.state.session_factory() as session:
        document = await execute_care_artifact_cleanup(
            session,
            client,
            layout,
            scope,
            cleanup_id="care-cleanup-a0-standard-0001",
            expected_objects=objects,
            confirmed_scope_sha256=str(scope.document(layout)["scope_sha256"]),
            subject="benchmark-cleanup-worker",
            reason="Superseded derived event partition after a verified re-import.",
        )
    assert document["status"] == "completed"
    assert document["deleted_count"] == 2
    assert document["raw_layer_deletion_allowed"] is False
    assert client.list_calls == [(layout.bucket, prefix + "/", True)]
    assert client.removed == sorted(objects)


@pytest.mark.parametrize(
    "scope",
    [
        CareArtifactCleanupScope(
            dataset_id="care",
            dataset_version="v6",
            dataset_sha256=DATASET_SHA256,
            layer="predictions",
            model_id="care-model",
            run_id="care-run-0001",
        ),
        CareArtifactCleanupScope(
            dataset_id="care",
            dataset_version="v6",
            dataset_sha256=DATASET_SHA256,
            layer="reports",
            model_id="care-model",
            run_id="care-run-0001",
        ),
    ],
)
def test_care_run_cleanup_prefix_is_model_and_run_scoped(
    scope: CareArtifactCleanupScope,
) -> None:
    prefix = scope.object_prefix(CareObjectStorageLayout())
    assert "model=care-model/run=care-run-0001" in prefix
    assert prefix.startswith("care/v6/")


@pytest.mark.asyncio
async def test_care_cleanup_rejects_raw_cross_scope_drift_and_partial_failure(
    app: FastAPI,
) -> None:
    with pytest.raises(BenchmarkArtifactScopeError, match="raw or unknown"):
        CareArtifactCleanupScope(
            dataset_id="care",
            dataset_version="v6",
            dataset_sha256=DATASET_SHA256,
            layer=cast(Any, "raw"),
            model_id="model",
            run_id="run",
        )
    layout = CareObjectStorageLayout()
    scope = _event_scope()
    prefix = scope.object_prefix(layout)
    valid_key = f"{prefix}/data.parquet"
    outside_key = "care/v6/standard/farm=A/event=1/data.parquet"
    async with app.state.session_factory() as session:
        with pytest.raises(BenchmarkArtifactScopeError, match="escaped"):
            await execute_care_artifact_cleanup(
                session,
                _CleanupClient({valid_key: OBJECT_SHA256}),
                layout,
                scope,
                cleanup_id="care-cleanup-outside-0001",
                expected_objects={outside_key: OBJECT_SHA256},
                confirmed_scope_sha256=str(scope.document(layout)["scope_sha256"]),
                subject="worker",
                reason="verified cleanup",
            )
        with pytest.raises(BenchmarkArtifactScopeError, match="listing differs"):
            await execute_care_artifact_cleanup(
                session,
                _CleanupClient(
                    {valid_key: OBJECT_SHA256, f"{prefix}/unexpected.json": DATASET_SHA256}
                ),
                layout,
                scope,
                cleanup_id="care-cleanup-list-drift-0001",
                expected_objects={valid_key: OBJECT_SHA256},
                confirmed_scope_sha256=str(scope.document(layout)["scope_sha256"]),
                subject="worker",
                reason="verified cleanup",
            )
        with pytest.raises(BenchmarkArtifactScopeError, match="confirmation"):
            await execute_care_artifact_cleanup(
                session,
                _CleanupClient({valid_key: OBJECT_SHA256}),
                layout,
                scope,
                cleanup_id="care-cleanup-confirmation-0001",
                expected_objects={valid_key: OBJECT_SHA256},
                confirmed_scope_sha256=DATASET_SHA256,
                subject="worker",
                reason="verified cleanup",
            )
        with pytest.raises(BenchmarkArtifactCleanupError, match="partial failure") as failure:
            await execute_care_artifact_cleanup(
                session,
                _CleanupClient({valid_key: OBJECT_SHA256}, fail_on=valid_key),
                layout,
                scope,
                cleanup_id="care-cleanup-partial-0001",
                expected_objects={valid_key: OBJECT_SHA256},
                confirmed_scope_sha256=str(scope.document(layout)["scope_sha256"]),
                subject="worker",
                reason="verified cleanup",
            )
    assert failure.value.audit_document["status"] == "failed"
    assert failure.value.audit_document["deleted_objects"] == []
    assert failure.value.audit_document["failed_object"] == valid_key
    async with app.state.session_factory() as session:
        failed_events = list(
            (
                await session.scalars(
                    select(DomainEvent)
                    .where(DomainEvent.aggregate_id == "care-cleanup-partial-0001")
                    .order_by(DomainEvent.sequence.asc())
                )
            ).all()
        )
    assert [event.event_type for event in failed_events] == [
        "benchmark.cleanup.started",
        "benchmark.cleanup.failed",
    ]


@pytest.mark.asyncio
async def test_care_cleanup_audit_is_durable_and_contains_no_credentials(
    app: FastAPI,
) -> None:
    layout = CareObjectStorageLayout()
    scope = _event_scope()
    key = f"{scope.object_prefix(layout)}/data.parquet"
    client = _CleanupClient({key: OBJECT_SHA256})
    async with app.state.session_factory() as session:
        document = await execute_care_artifact_cleanup(
            session,
            client,
            layout,
            scope,
            cleanup_id="care-cleanup-a0-0001",
            expected_objects={key: OBJECT_SHA256},
            confirmed_scope_sha256=str(scope.document(layout)["scope_sha256"]),
            subject="benchmark-cleanup-worker",
            reason="verified cleanup",
        )
        repeated = await execute_care_artifact_cleanup(
            session,
            client,
            layout,
            scope,
            cleanup_id="care-cleanup-a0-0001",
            expected_objects={key: OBJECT_SHA256},
            confirmed_scope_sha256=str(scope.document(layout)["scope_sha256"]),
            subject="benchmark-cleanup-worker",
            reason="verified cleanup",
        )
        assert repeated == document
        assert client.removed == [key]
    async with app.state.session_factory() as session:
        persisted = list(
            (
                await session.scalars(
                    select(DomainEvent)
                    .where(DomainEvent.aggregate_id == "care-cleanup-a0-0001")
                    .order_by(DomainEvent.sequence.asc())
                )
            ).all()
        )
    assert [event.event_type for event in persisted] == [
        "benchmark.cleanup.started",
        "benchmark.cleanup.completed",
    ]
    assert all(event.aggregate_type == "benchmark_cleanup" for event in persisted)
    serialized = str([event.payload for event in persisted]).casefold()
    assert "secret" not in serialized
    assert "token" not in serialized
    assert "password" not in serialized
