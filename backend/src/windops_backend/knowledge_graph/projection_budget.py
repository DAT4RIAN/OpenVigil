"""Shared projection limits and accounting; owns process-wide tracing coordination."""

from __future__ import annotations

import sys
import threading
import tracemalloc
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from math import ceil
from time import monotonic
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from windops_backend.config import Settings
_MEMORY_ACCOUNTING_SAFETY_FACTOR = 1.50
_PYTHON_MEMORY_HEADROOM_RATIO = 0.15
_TRACEMALLOC_LOCK = threading.Lock()
_TRACEMALLOC_USERS = 0
_TRACEMALLOC_STARTED_BY_PROJECTION = False


class ProjectionLimitExceeded(RuntimeError):
    """The authoritative projection exceeded a configured production budget."""


def _deep_sizeof(value: object, seen: set[int] | None = None) -> int:
    """Return the owned Python heap size of a projection value.

    The traversal intentionally ignores SQLAlchemy's instance-state object so
    a bounded source row is charged for its loaded column payload rather than
    for the shared Session identity map. Shared children are counted once per
    value traversal; separate live containers are charged separately.
    """

    visited = seen if seen is not None else set()
    identity = id(value)
    if identity in visited:
        return 0
    visited.add(identity)
    size = sys.getsizeof(value)
    if value is None or isinstance(value, str | bytes | int | float | bool):
        return size
    if isinstance(value, Mapping):
        return size + sum(
            _deep_sizeof(key, visited) + _deep_sizeof(item, visited)
            for key, item in value.items()
            if key != "_sa_instance_state"
        )
    if isinstance(value, tuple | list | set | frozenset):
        return size + sum(_deep_sizeof(item, visited) for item in value)
    if is_dataclass(value) and not isinstance(value, type):
        return size + sum(
            _deep_sizeof(getattr(value, field.name), visited) for field in fields(value)
        )
    state = getattr(value, "__dict__", None)
    if isinstance(state, dict):
        return size + _deep_sizeof(
            {key: item for key, item in state.items() if key != "_sa_instance_state"},
            visited,
        )
    return size


def _conservative_memory_bytes(value: object, *, entry_overhead: int = 0) -> int:
    measured = _deep_sizeof(value) + max(0, entry_overhead)
    return max(64, ceil(measured * _MEMORY_ACCOUNTING_SAFETY_FACTOR))


class _PythonPeakMemorySampler:
    """Measure incremental Python allocations without disrupting external tracing."""

    def __init__(self) -> None:
        global _TRACEMALLOC_STARTED_BY_PROJECTION, _TRACEMALLOC_USERS

        with _TRACEMALLOC_LOCK:
            if not tracemalloc.is_tracing():
                tracemalloc.start(1)
                _TRACEMALLOC_STARTED_BY_PROJECTION = True
            _TRACEMALLOC_USERS += 1
        self._closed = False
        self._baseline_current, self._baseline_peak = tracemalloc.get_traced_memory()
        self.peak_increment_bytes = 0

    def sample(self) -> int:
        if self._closed or not tracemalloc.is_tracing():
            return self.peak_increment_bytes
        current, peak = tracemalloc.get_traced_memory()
        current_increment = max(0, current - self._baseline_current)
        new_global_peak = max(0, peak - max(self._baseline_current, self._baseline_peak))
        self.peak_increment_bytes = max(
            self.peak_increment_bytes,
            current_increment,
            new_global_peak,
        )
        return self.peak_increment_bytes

    def close(self) -> None:
        global _TRACEMALLOC_STARTED_BY_PROJECTION, _TRACEMALLOC_USERS

        if self._closed:
            return
        self.sample()
        self._closed = True
        with _TRACEMALLOC_LOCK:
            _TRACEMALLOC_USERS -= 1
            if _TRACEMALLOC_USERS == 0 and _TRACEMALLOC_STARTED_BY_PROJECTION:
                tracemalloc.stop()
                _TRACEMALLOC_STARTED_BY_PROJECTION = False


@dataclass(frozen=True)
class ProjectionLimits:
    batch_size: int = 500
    max_source_rows: int = 250_000
    max_nodes: int = 250_000
    max_relationships: int = 500_000
    max_source_bytes: int = 512 * 1024 * 1024
    max_graph_bytes: int = 256 * 1024 * 1024
    max_estimated_memory_bytes: int = 256 * 1024 * 1024
    max_runtime_seconds: float = 300.0

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls(
            batch_size=settings.knowledge_graph_projection_batch_size,
            max_source_rows=settings.knowledge_graph_projection_max_source_rows,
            max_nodes=settings.knowledge_graph_projection_max_nodes,
            max_relationships=settings.knowledge_graph_projection_max_relationships,
            max_source_bytes=(
                settings.knowledge_graph_projection_max_source_megabytes * 1024 * 1024
            ),
            max_graph_bytes=(settings.knowledge_graph_projection_max_graph_megabytes * 1024 * 1024),
            max_estimated_memory_bytes=(
                settings.knowledge_graph_projection_max_memory_megabytes * 1024 * 1024
            ),
            max_runtime_seconds=settings.knowledge_graph_projection_max_runtime_seconds,
        )

    def __post_init__(self) -> None:
        for name in (
            "batch_size",
            "max_source_rows",
            "max_nodes",
            "max_relationships",
            "max_source_bytes",
            "max_graph_bytes",
            "max_estimated_memory_bytes",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.max_runtime_seconds <= 0:
            raise ValueError("max_runtime_seconds must be positive")


class _ProjectionBudget:
    def __init__(self, limits: ProjectionLimits) -> None:
        self.limits = limits
        self.started_at = monotonic()
        self.source_rows = 0
        self.source_bytes = 0
        self.graph_bytes = 0
        self.estimated_memory_bytes = 0
        self.peak_memory_bytes = 0
        self.actual_peak_memory_bytes = 0
        self._memory_sampler = _PythonPeakMemorySampler()

    @property
    def python_memory_limit_bytes(self) -> int:
        return max(
            1,
            int(self.limits.max_estimated_memory_bytes * (1.0 - _PYTHON_MEMORY_HEADROOM_RATIO)),
        )

    def check_actual_memory(self) -> None:
        self.actual_peak_memory_bytes = self._memory_sampler.sample()
        if self.actual_peak_memory_bytes > self.python_memory_limit_bytes:
            raise ProjectionLimitExceeded(
                "knowledge graph projection actual Python memory budget exceeded"
            )
        self.check_runtime()

    def close(self) -> None:
        self.actual_peak_memory_bytes = self._memory_sampler.sample()
        self._memory_sampler.close()

    def check_runtime(self) -> None:
        if monotonic() - self.started_at > self.limits.max_runtime_seconds:
            raise ProjectionLimitExceeded("knowledge graph projection runtime budget exceeded")

    def consume_source_rows(self, count: int, byte_count: int = 0) -> None:
        self.source_rows += count
        self.source_bytes += max(0, byte_count)
        if self.source_rows > self.limits.max_source_rows:
            raise ProjectionLimitExceeded("knowledge graph projection source-row budget exceeded")
        if self.source_bytes > self.limits.max_source_bytes:
            raise ProjectionLimitExceeded("knowledge graph projection source-byte budget exceeded")
        self.check_actual_memory()

    def reserve_memory(self, delta: int) -> None:
        self.estimated_memory_bytes += delta
        if self.estimated_memory_bytes > self.limits.max_estimated_memory_bytes:
            raise ProjectionLimitExceeded("knowledge graph projection memory budget exceeded")
        if self.estimated_memory_bytes < 0:  # defensive accounting guard
            self.estimated_memory_bytes = 0
        self.peak_memory_bytes = max(self.peak_memory_bytes, self.estimated_memory_bytes)
        self.check_actual_memory()

    def reserve_graph(self, delta: int) -> None:
        self.graph_bytes += delta
        if self.graph_bytes > self.limits.max_graph_bytes:
            raise ProjectionLimitExceeded("knowledge graph projection graph-byte budget exceeded")
        if self.graph_bytes < 0:  # defensive accounting guard
            self.graph_bytes = 0


class _BudgetedDict[Key, Value](dict[Key, Value]):
    """A projection-owned mapping that accounts every live key/value entry."""

    def __init__(self, budget: _ProjectionBudget) -> None:
        super().__init__()
        self._budget = budget
        self._reserved_bytes = _conservative_memory_bytes({})
        self._budget.reserve_memory(self._reserved_bytes)

    @staticmethod
    def _entry_bytes(key: Key, value: Value) -> int:
        return _conservative_memory_bytes((key, value), entry_overhead=64)

    def __setitem__(self, key: Key, value: Value) -> None:
        previous_size = self._entry_bytes(key, self[key]) if key in self else 0
        next_size = self._entry_bytes(key, value)
        self._budget.reserve_memory(next_size - previous_size)
        super().__setitem__(key, value)
        self._reserved_bytes += next_size - previous_size
        self._budget.check_actual_memory()

    def setdefault(self, key: Key, default: Value) -> Value:
        if key in self:
            return self[key]
        self[key] = default
        return default

    def release(self) -> None:
        if self._reserved_bytes <= 0:
            return
        super().clear()
        self._budget.reserve_memory(-self._reserved_bytes)
        self._reserved_bytes = 0
