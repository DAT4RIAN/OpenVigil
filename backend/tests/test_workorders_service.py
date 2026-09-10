from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from windops_backend.enums import TaskStatus, WorkOrderStatus
from windops_backend.errors import InvalidTransitionError, NotFoundError
from windops_backend.schemas import TaskCompletionRequest
from windops_backend.services.workorders import complete_task


def _request() -> TaskCompletionRequest:
    return TaskCompletionRequest(
        result="fixture",
        artifact_uri="minio://windops-field-evidence/work-order/task/evidence.json",
        artifact_sha256="a" * 64,
        measurement={"fixture": "value"},
    )


@pytest.mark.asyncio
async def test_complete_task_rejects_missing_work_order_and_task() -> None:
    session = AsyncMock()
    session.scalar.return_value = None
    with pytest.raises(NotFoundError):
        await complete_task(session, "missing-work-order", "task-1", _request(), object())

    session.scalar.return_value = SimpleNamespace(id="work-order-1", status="scheduled")
    session.get.return_value = None
    with pytest.raises(NotFoundError):
        await complete_task(session, "work-order-1", "missing-task", _request(), object())


@pytest.mark.asyncio
async def test_complete_task_is_idempotent_for_completed_task() -> None:
    session = AsyncMock()
    session.scalar.return_value = SimpleNamespace(id="work-order-1", status="scheduled")
    session.get.return_value = SimpleNamespace(
        id="task-1",
        work_order_id="work-order-1",
        status=TaskStatus.COMPLETED.value,
    )
    result = await complete_task(session, "work-order-1", "task-1", _request(), object())
    assert result == {
        "task_id": "task-1",
        "task_status": TaskStatus.COMPLETED.value,
        "work_order_status": "scheduled",
        "already_completed": True,
    }


@pytest.mark.asyncio
async def test_complete_task_rejects_completed_work_order() -> None:
    session = AsyncMock()
    session.scalar.return_value = SimpleNamespace(
        id="work-order-1", status=WorkOrderStatus.COMPLETED.value
    )
    session.get.return_value = SimpleNamespace(
        id="task-1",
        work_order_id="work-order-1",
        status=TaskStatus.PENDING.value,
    )
    with pytest.raises(InvalidTransitionError):
        await complete_task(session, "work-order-1", "task-1", _request(), object())
