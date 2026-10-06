"""Bounded SQL source traversal with shared projection accounting."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from windops_backend.knowledge_graph.projection_budget import (
    _conservative_memory_bytes,
    _ProjectionBudget,
)
from windops_backend.models import ScadaSample


def _estimated_row_bytes(row: object) -> int:
    values: object
    if hasattr(row, "__dict__"):
        values = {key: value for key, value in vars(row).items() if key != "_sa_instance_state"}
    elif hasattr(row, "_mapping"):
        values = dict(row._mapping)
    elif isinstance(row, tuple):
        values = row
    else:
        values = row
    return _conservative_memory_bytes(values, entry_overhead=128)


async def _iter_bounded_scalar_rows[ProjectionRow](
    session: AsyncSession,
    statement: Select[tuple[ProjectionRow]],
    *,
    budget: _ProjectionBudget,
    key_column: Any | None = None,
    key_attribute: str | None = None,
) -> AsyncIterator[ProjectionRow]:
    last_key: object | None = None
    while True:
        page_statement = statement
        if key_column is not None and last_key is not None:
            page_statement = page_statement.where(key_column > last_key)
        if key_column is not None:
            page_statement = page_statement.limit(budget.limits.batch_size)
        stream = await session.stream_scalars(
            page_statement.execution_options(yield_per=budget.limits.batch_size)
        )
        page_rows: list[ProjectionRow] = []
        try:
            async for partition in stream.partitions(budget.limits.batch_size):
                page_rows.extend(partition)
        finally:
            await stream.close()
        if not page_rows:
            break
        budget.check_actual_memory()
        partition_bytes = max(
            _conservative_memory_bytes(page_rows),
            _conservative_memory_bytes([None] * len(page_rows))
            + sum(_estimated_row_bytes(row) for row in page_rows),
        )
        budget.consume_source_rows(len(page_rows), partition_bytes)
        budget.reserve_memory(partition_bytes)
        try:
            for row in page_rows:
                yield row
        finally:
            budget.reserve_memory(-partition_bytes)
            budget.check_actual_memory()
        if key_column is None or key_attribute is None or len(page_rows) < budget.limits.batch_size:
            break
        last_key = getattr(page_rows[-1], key_attribute)


async def _iter_bounded_sensor_rows(
    session: AsyncSession,
    *,
    budget: _ProjectionBudget,
) -> AsyncIterator[tuple[str, str, str]]:
    statement = (
        select(ScadaSample.turbine_id, ScadaSample.variable, ScadaSample.unit)
        .distinct()
        .order_by(ScadaSample.turbine_id, ScadaSample.variable, ScadaSample.unit)
        .execution_options(yield_per=budget.limits.batch_size)
    )
    stream = await session.stream(statement)
    try:
        async for partition in stream.partitions(budget.limits.batch_size):
            budget.check_actual_memory()
            partition_bytes = max(
                _conservative_memory_bytes(partition),
                _conservative_memory_bytes([None] * len(partition))
                + sum(_estimated_row_bytes(row) for row in partition),
            )
            budget.consume_source_rows(len(partition), partition_bytes)
            budget.reserve_memory(partition_bytes)
            try:
                for row in partition:
                    yield (str(row[0]), str(row[1]), str(row[2]))
            finally:
                budget.reserve_memory(-partition_bytes)
                budget.check_actual_memory()
    finally:
        await stream.close()
