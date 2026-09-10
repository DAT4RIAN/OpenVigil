from __future__ import annotations

import hashlib
import heapq
import json
import logging
import re
import sys
import threading
import tracemalloc
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, datetime
from math import ceil
from time import monotonic
from typing import TYPE_CHECKING, Any, Self

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from windops_backend.knowledge_graph.domain import (
    GraphNode,
    GraphProperties,
    GraphRelationship,
    GraphSnapshot,
    NodeType,
    RelationshipType,
    graph_data_scope,
    graph_uid,
)
from windops_backend.models import (
    Alarm,
    Decision,
    Evidence,
    KnowledgeCase,
    KnowledgeDocument,
    Mission,
    Resource,
    ResourceReservation,
    ScadaSample,
    Turbine,
    WindFarm,
    WorkOrder,
    WorkOrderTask,
)
from windops_backend.storage import FieldTaskEvidence

if TYPE_CHECKING:
    from windops_backend.config import Settings

KNOWLEDGE_GRAPH_PROJECTION_ID = "windops-operational-knowledge-v1"
KNOWLEDGE_GRAPH_MODEL_VERSION = "2026.08.1"
_MEMORY_ACCOUNTING_SAFETY_FACTOR = 1.50
_PYTHON_MEMORY_HEADROOM_RATIO = 0.15
_SNAPSHOT_HANDOFF_BYTES_PER_ITEM = 160
_TRACEMALLOC_LOCK = threading.Lock()
_TRACEMALLOC_USERS = 0
_TRACEMALLOC_STARTED_BY_PROJECTION = False
logger = logging.getLogger(__name__)


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


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return normalized or "unknown"


def _subsystem_for_variable(variable: str) -> str:
    normalized = variable.lower()
    if "main_bearing" in normalized or "main-bearing" in normalized:
        return "main_bearing"
    if "gearbox" in normalized:
        return "gearbox"
    if "generator" in normalized:
        return "generator"
    return "turbine"


class _ProjectionBuilder:
    def __init__(self, limits: ProjectionLimits, budget: _ProjectionBudget) -> None:
        self.limits = limits
        self.budget = budget
        self.nodes: dict[str, GraphNode] = {}
        self.relationships: dict[str, GraphRelationship] = {}
        self._largest_write_rows: list[int] = []
        self.budget.reserve_memory(
            _conservative_memory_bytes(self.nodes)
            + _conservative_memory_bytes(self.relationships)
            + _conservative_memory_bytes([0] * min(self.limits.batch_size, self.limits.max_nodes))
        )
        self.estimated_memory_bytes = 0

    def _remember_write_row_size(self, size: int) -> None:
        if len(self._largest_write_rows) < self.limits.batch_size:
            heapq.heappush(self._largest_write_rows, size)
        elif size > self._largest_write_rows[0]:
            heapq.heapreplace(self._largest_write_rows, size)

    def _reserve_memory(
        self,
        *,
        previous_graph_size: int,
        next_graph_size: int,
        previous_memory_size: int,
        next_memory_size: int,
    ) -> None:
        self.budget.reserve_graph(next_graph_size - previous_graph_size)
        self.budget.reserve_memory(next_memory_size - previous_memory_size)
        self.estimated_memory_bytes = self.budget.estimated_memory_bytes

    def node(
        self, node_type: NodeType, entity_id: str, **properties: str | int | float | bool | None
    ) -> str:
        uid = graph_uid(node_type, entity_id)
        properties.setdefault("dataScope", graph_data_scope(node_type))
        clean: GraphProperties = {
            key: value
            for key, value in properties.items()
            if value is None or isinstance(value, str | int | float | bool)
        }
        node = GraphNode(
            uid=uid,
            node_type=node_type,
            entity_id=entity_id,
            properties=clean,
        )
        previous = self.nodes.get(uid)
        previous_graph_size = (
            len(_json(previous.as_dict()).encode("utf-8")) + 128 if previous is not None else 0
        )
        next_graph_size = len(_json(node.as_dict()).encode("utf-8")) + 128
        previous_memory_size = (
            _conservative_memory_bytes((uid, previous), entry_overhead=64)
            if previous is not None
            else 0
        )
        next_memory_size = _conservative_memory_bytes((uid, node), entry_overhead=64)
        self._reserve_memory(
            previous_graph_size=previous_graph_size,
            next_graph_size=next_graph_size,
            previous_memory_size=previous_memory_size,
            next_memory_size=next_memory_size,
        )
        self.nodes[uid] = node
        self._remember_write_row_size(
            _conservative_memory_bytes(node.as_dict(), entry_overhead=384)
        )
        self.budget.check_actual_memory()
        if len(self.nodes) > self.limits.max_nodes:
            raise ProjectionLimitExceeded("knowledge graph projection node budget exceeded")
        return uid

    def relationship(
        self,
        relationship_type: RelationshipType,
        source_uid: str,
        target_uid: str,
        *,
        qualifier: str = "",
        **properties: str | int | float | bool | None,
    ) -> str:
        identity = f"{relationship_type.value}:{source_uid}->{target_uid}"
        if qualifier:
            identity = f"{identity}:{qualifier}"
        clean: GraphProperties = {
            key: value
            for key, value in properties.items()
            if value is None or isinstance(value, str | int | float | bool)
        }
        relationship = GraphRelationship(
            uid=identity,
            relationship_type=relationship_type,
            source_uid=source_uid,
            target_uid=target_uid,
            properties=clean,
        )
        previous = self.relationships.get(identity)
        previous_graph_size = (
            len(_json(previous.as_dict()).encode("utf-8")) + 128 if previous is not None else 0
        )
        next_graph_size = len(_json(relationship.as_dict()).encode("utf-8")) + 128
        previous_memory_size = (
            _conservative_memory_bytes((identity, previous), entry_overhead=64)
            if previous is not None
            else 0
        )
        next_memory_size = _conservative_memory_bytes((identity, relationship), entry_overhead=64)
        self._reserve_memory(
            previous_graph_size=previous_graph_size,
            next_graph_size=next_graph_size,
            previous_memory_size=previous_memory_size,
            next_memory_size=next_memory_size,
        )
        self.relationships[identity] = relationship
        self._remember_write_row_size(
            _conservative_memory_bytes(relationship.as_dict(), entry_overhead=512)
        )
        self.budget.check_actual_memory()
        if len(self.relationships) > self.limits.max_relationships:
            raise ProjectionLimitExceeded("knowledge graph projection relationship budget exceeded")
        return identity

    def snapshot(self, projection_sequence: str | None = None) -> GraphSnapshot:
        item_count = len(self.nodes) + len(self.relationships)
        handoff_headroom = item_count * _SNAPSHOT_HANDOFF_BYTES_PER_ITEM
        serialization_headroom = sum(self._largest_write_rows)
        self.budget.reserve_memory(handoff_headroom + serialization_headroom)
        try:
            nodes = tuple(self.nodes[uid] for uid in sorted(self.nodes))
            relationships = tuple(self.relationships[uid] for uid in sorted(self.relationships))
            self.budget.check_actual_memory()
            revision_hasher = hashlib.sha256()
            for node in nodes:
                revision_hasher.update(b"node\0")
                revision_hasher.update(_json(node.as_dict()).encode("utf-8"))
                revision_hasher.update(b"\n")
            for relationship in relationships:
                revision_hasher.update(b"relationship\0")
                revision_hasher.update(_json(relationship.as_dict()).encode("utf-8"))
                revision_hasher.update(b"\n")
            revision = revision_hasher.hexdigest()
            generated_at = datetime.now(UTC)
            snapshot = GraphSnapshot(
                projection_id=KNOWLEDGE_GRAPH_PROJECTION_ID,
                projection_sequence=projection_sequence or f"{generated_at.isoformat()}:direct",
                source_revision=revision,
                generated_at=generated_at,
                nodes=nodes,
                relationships=relationships,
            )
            self.budget.check_actual_memory()
            return snapshot
        finally:
            self.budget.reserve_memory(-(handoff_headroom + serialization_headroom))


@dataclass(frozen=True, slots=True)
class _MissionContext:
    mission_id: str
    mission_uid: str
    turbine_id: str
    alarm_id: str
    revision: int
    failure_uid: str | None
    confidence: float


@dataclass(frozen=True, slots=True)
class _WorkOrderContext:
    work_order_uid: str
    turbine_id: str
    mission_id: str


@dataclass(frozen=True, slots=True)
class _TaskContext:
    work_order_id: str


@dataclass(frozen=True, slots=True)
class _ResourceContext:
    resource_uid: str
    resource_type: str


async def build_knowledge_graph_snapshot(
    session: AsyncSession,
    *,
    projection_sequence: str | None = None,
    limits: ProjectionLimits | None = None,
) -> GraphSnapshot:
    """Build a graph with conservative accounting and measured Python peak memory."""

    effective_limits = limits or ProjectionLimits()
    budget = _ProjectionBudget(effective_limits)
    outcome = "succeeded"
    try:
        return await _build_knowledge_graph_snapshot(
            session,
            projection_sequence=projection_sequence,
            effective_limits=effective_limits,
            budget=budget,
        )
    except Exception:
        outcome = "failed"
        raise
    finally:
        budget.close()
        logger.info(
            "knowledge graph projection memory outcome=%s actual_peak_bytes=%d "
            "accounted_peak_bytes=%d configured_limit_bytes=%d python_limit_bytes=%d",
            outcome,
            budget.actual_peak_memory_bytes,
            budget.peak_memory_bytes,
            effective_limits.max_estimated_memory_bytes,
            budget.python_memory_limit_bytes,
        )


async def _build_knowledge_graph_snapshot(
    session: AsyncSession,
    *,
    projection_sequence: str | None,
    effective_limits: ProjectionLimits,
    budget: _ProjectionBudget,
) -> GraphSnapshot:
    """Retain bounded indexes while source ORM partitions are promptly released.

    Each source table is consumed in a key-ordered cursor partition.  ORM rows
    are released after the partition is processed; only the scalar foreign-key
    indexes required by later phases remain.  The shared budget accounts for
    partition bytes, graph objects, and those indexes together.
    """

    builder = _ProjectionBuilder(effective_limits, budget)

    farm_tenants = _BudgetedDict[str, str](budget)
    farm_uids = _BudgetedDict[str, str](budget)
    async for farm in _iter_bounded_scalar_rows(
        session,
        select(WindFarm).order_by(WindFarm.id),
        budget=budget,
        key_column=WindFarm.id,
        key_attribute="id",
    ):
        farm_tenants[farm.id] = farm.tenant_id
        farm_uids[farm.id] = builder.node(
            NodeType.WIND_FARM,
            farm.id,
            tenantId=farm.tenant_id,
            name=farm.name,
            capacityMw=farm.capacity_mw,
            source="postgresql",
            createdAt=_iso(farm.created_at),
        )

    turbine_scope = _BudgetedDict[str, tuple[str | None, str]](budget)
    turbine_uids = _BudgetedDict[str, str](budget)
    subsystem_uids = _BudgetedDict[tuple[str, str], str](budget)

    def ensure_subsystem(turbine_id: str, subsystem: str) -> str:
        key = (turbine_id, _slug(subsystem))
        existing = subsystem_uids.get(key)
        if existing is not None:
            return existing
        tenant_id, wind_farm_id = turbine_scope.get(turbine_id, (None, ""))
        uid = builder.node(
            NodeType.SUBSYSTEM,
            f"{turbine_id}:{key[1]}",
            tenantId=tenant_id,
            windFarmId=wind_farm_id,
            turbineId=turbine_id,
            subsystemKey=key[1],
            name=key[1].replace("_", " ").title(),
            source="derived-from-authoritative-domain",
        )
        subsystem_uids[key] = uid
        turbine_uid = turbine_uids.get(turbine_id)
        if turbine_uid is not None:
            builder.relationship(RelationshipType.HAS_SUBSYSTEM, turbine_uid, uid)
        return uid

    async for turbine in _iter_bounded_scalar_rows(
        session,
        select(Turbine).order_by(Turbine.id),
        budget=budget,
        key_column=Turbine.id,
        key_attribute="id",
    ):
        tenant_id = farm_tenants.get(turbine.wind_farm_id)
        turbine_scope[turbine.id] = (tenant_id, turbine.wind_farm_id)
        turbine_uid = builder.node(
            NodeType.TURBINE,
            turbine.id,
            tenantId=tenant_id,
            windFarmId=turbine.wind_farm_id,
            model=turbine.model,
            status=turbine.status,
            healthScore=turbine.health_score,
            source="postgresql",
            updatedAt=_iso(turbine.updated_at),
        )
        turbine_uids[turbine.id] = turbine_uid
        if turbine.wind_farm_id in farm_uids:
            builder.relationship(
                RelationshipType.HAS_TURBINE,
                farm_uids[turbine.wind_farm_id],
                turbine_uid,
            )
        ensure_subsystem(turbine.id, "main_bearing")

    farm_tenants.release()
    farm_uids.release()

    async for turbine_id, variable, unit in _iter_bounded_sensor_rows(session, budget=budget):
        subsystem_uid = ensure_subsystem(turbine_id, _subsystem_for_variable(variable))
        tenant_id, wind_farm_id = turbine_scope.get(turbine_id, (None, None))
        sensor_uid = builder.node(
            NodeType.SENSOR,
            f"{turbine_id}:{variable}",
            tenantId=tenant_id,
            windFarmId=wind_farm_id,
            turbineId=turbine_id,
            variable=variable,
            unit=unit,
            source="postgresql-distinct-scada-identity",
        )
        builder.relationship(RelationshipType.MONITORED_BY, subsystem_uid, sensor_uid)

    mission_context = _BudgetedDict[str, _MissionContext](budget)
    mission_by_alarm = _BudgetedDict[str, _MissionContext](budget)
    failure_mode_uids = _BudgetedDict[str, str](budget)
    async for mission in _iter_bounded_scalar_rows(
        session,
        select(Mission).order_by(Mission.id),
        budget=budget,
        key_column=Mission.id,
        key_attribute="id",
    ):
        tenant_id, wind_farm_id = turbine_scope.get(mission.turbine_id, (None, None))
        diagnosis_value = mission.public_state.get("diagnosis", {})
        diagnosis = diagnosis_value if isinstance(diagnosis_value, dict) else {}
        failure_uid: str | None = None
        if diagnosis.get("failure_mode"):
            failure_mode_id = _slug(str(diagnosis["failure_mode"]))
            failure_uid = failure_mode_uids.get(failure_mode_id)
            if failure_uid is None:
                failure_uid = builder.node(
                    NodeType.FAILURE_MODE,
                    failure_mode_id,
                    name=str(diagnosis["failure_mode"]).replace("_", " ").title(),
                    severity=str(diagnosis.get("severity", "unknown")),
                    source="mission-public-diagnosis",
                    modelVersion=KNOWLEDGE_GRAPH_MODEL_VERSION,
                )
                failure_mode_uids[failure_mode_id] = failure_uid
        mission_uid = builder.node(
            NodeType.MISSION,
            mission.id,
            tenantId=tenant_id,
            windFarmId=wind_farm_id,
            turbineId=mission.turbine_id,
            alarmId=mission.alarm_id,
            title=mission.title,
            status=mission.status,
            revision=mission.revision,
            source="postgresql",
            createdAt=_iso(mission.created_at),
            updatedAt=_iso(mission.updated_at),
        )
        confidence = float(diagnosis.get("confidence", 0.0))
        context = _MissionContext(
            mission.id,
            mission_uid,
            mission.turbine_id,
            mission.alarm_id,
            mission.revision,
            failure_uid,
            confidence,
        )
        mission_context[mission.id] = context
        mission_by_alarm[mission.alarm_id] = context
        if failure_uid is not None:
            builder.relationship(
                RelationshipType.INDICATES,
                mission_uid,
                failure_uid,
                qualifier=mission.id,
                confidence=float(diagnosis.get("confidence", 0.0)),
                source="postgresql-mission-public-state",
                observedAt=_iso(mission.updated_at),
                validFrom=_iso(mission.updated_at),
                validTo=None,
                modelVersion=KNOWLEDGE_GRAPH_MODEL_VERSION,
                revision=mission.revision,
            )

    failure_mode_uids.release()

    async for alarm in _iter_bounded_scalar_rows(
        session,
        select(Alarm).order_by(Alarm.id),
        budget=budget,
        key_column=Alarm.id,
        key_attribute="id",
    ):
        tenant_id, wind_farm_id = turbine_scope.get(alarm.turbine_id, (None, None))
        alarm_uid = builder.node(
            NodeType.ALARM,
            alarm.id,
            tenantId=tenant_id,
            windFarmId=wind_farm_id,
            turbineId=alarm.turbine_id,
            code=alarm.code,
            title=alarm.title,
            severity=alarm.severity,
            status=alarm.status,
            aiStatus=alarm.ai_status,
            source="postgresql",
            triggeredAt=_iso(alarm.triggered_at),
        )
        subsystem_uid = ensure_subsystem(alarm.turbine_id, alarm.subsystem)
        builder.relationship(RelationshipType.AFFECTS, alarm_uid, subsystem_uid)
        anomaly_uid = builder.node(
            NodeType.ANOMALY,
            f"{alarm.id}:semantic-anomaly",
            tenantId=tenant_id,
            windFarmId=wind_farm_id,
            alarmId=alarm.id,
            turbineId=alarm.turbine_id,
            kind=alarm.code,
            summary=alarm.title,
            observedAt=_iso(alarm.triggered_at),
            source="persisted-alarm-evidence",
            evidenceJson=_json(alarm.evidence),
        )
        builder.relationship(
            RelationshipType.TRIGGERED,
            anomaly_uid,
            alarm_uid,
            observedAt=_iso(alarm.triggered_at),
            source="postgresql",
        )
        linked_mission_context = mission_by_alarm.get(alarm.id)
        if linked_mission_context is not None:
            builder.relationship(
                RelationshipType.TRIGGERED,
                alarm_uid,
                linked_mission_context.mission_uid,
                observedAt=_iso(alarm.triggered_at),
                source="postgresql-foreign-key",
            )
            if linked_mission_context.failure_uid is not None:
                builder.relationship(
                    RelationshipType.INDICATES,
                    anomaly_uid,
                    linked_mission_context.failure_uid,
                    qualifier=alarm.id,
                    confidence=linked_mission_context.confidence,
                    evidenceId=alarm.id,
                    source="persisted-alarm-and-mission-diagnosis",
                    observedAt=_iso(alarm.triggered_at),
                    validFrom=_iso(alarm.triggered_at),
                    validTo=None,
                    modelVersion=KNOWLEDGE_GRAPH_MODEL_VERSION,
                    revision=linked_mission_context.revision,
                )

    mission_by_alarm.release()
    subsystem_uids.release()

    passage_uids = _BudgetedDict[str, str](budget)
    async for document in _iter_bounded_scalar_rows(
        session,
        select(KnowledgeDocument).order_by(KnowledgeDocument.id),
        budget=budget,
        key_column=KnowledgeDocument.id,
        key_attribute="id",
    ):
        document_uid = builder.node(
            NodeType.KNOWLEDGE_DOCUMENT,
            document.id,
            tenantId=document.tenant_id,
            windFarmId=document.wind_farm_id,
            turbineId=document.turbine_id,
            title=document.title,
            documentType=document.document_type,
            citationUri=document.citation_uri,
            vectorized=document.vectorized,
            source="postgresql",
            updatedAt=_iso(document.updated_at),
        )
        passage_uid = builder.node(
            NodeType.KNOWLEDGE_PASSAGE,
            f"{document.id}#body",
            tenantId=document.tenant_id,
            windFarmId=document.wind_farm_id,
            turbineId=document.turbine_id,
            documentId=document.id,
            section="body",
            body=document.body,
            tokenEstimate=max(1, len(document.body.encode("utf-8")) // 4),
            citationUri=document.citation_uri,
            source="postgresql-knowledge-document",
            updatedAt=_iso(document.updated_at),
        )
        passage_uids[document.id] = passage_uid
        builder.relationship(RelationshipType.HAS_PASSAGE, document_uid, passage_uid)

    async for evidence in _iter_bounded_scalar_rows(
        session,
        select(Evidence).order_by(Evidence.id),
        budget=budget,
        key_column=Evidence.id,
        key_attribute="id",
    ):
        linked_mission = mission_context.get(evidence.mission_id)
        tenant_id, wind_farm_id = (
            turbine_scope.get(linked_mission.turbine_id, (None, None))
            if linked_mission is not None
            else (None, None)
        )
        stance = str(evidence.metrics.get("stance", "supporting")).strip().lower()
        relationship_type = (
            RelationshipType.CONTRADICTED_BY
            if stance == "contradicting"
            else RelationshipType.SUPPORTED_BY
        )
        evidence_uid = builder.node(
            NodeType.EVIDENCE,
            evidence.id,
            tenantId=tenant_id,
            windFarmId=wind_farm_id,
            turbineId=linked_mission.turbine_id if linked_mission is not None else None,
            missionId=evidence.mission_id,
            sourceKey=evidence.source_key,
            evidenceType=evidence.evidence_type,
            summary=evidence.summary,
            citationUri=evidence.citation_uri,
            retrievalMethod=evidence.retrieval_method,
            metricsJson=_json(evidence.metrics),
            sourceRefsJson=_json(evidence.source_refs),
            source="postgresql",
            createdAt=_iso(evidence.created_at),
        )
        if linked_mission is not None:
            builder.relationship(
                relationship_type, linked_mission.mission_uid, evidence_uid, stance=stance
            )
            if linked_mission.failure_uid is not None:
                builder.relationship(
                    relationship_type,
                    linked_mission.failure_uid,
                    evidence_uid,
                    qualifier=evidence.id,
                    evidenceId=evidence.id,
                    source="postgresql-evidence",
                    observedAt=_iso(evidence.created_at),
                    stance=stance,
                )
        if evidence.citation_uri:
            for document_id, passage_uid in passage_uids.items():
                if document_id in evidence.citation_uri:
                    builder.relationship(
                        RelationshipType.DERIVED_FROM,
                        evidence_uid,
                        passage_uid,
                        citationUri=evidence.citation_uri,
                        retrievalMethod=evidence.retrieval_method,
                    )

    passage_uids.release()

    async for decision in _iter_bounded_scalar_rows(
        session,
        select(Decision).order_by(Decision.id),
        budget=budget,
        key_column=Decision.id,
        key_attribute="id",
    ):
        linked_mission = mission_context.get(decision.mission_id)
        tenant_id, wind_farm_id = (
            turbine_scope.get(linked_mission.turbine_id, (None, None))
            if linked_mission is not None
            else (None, None)
        )
        decision_uid = builder.node(
            NodeType.DECISION,
            decision.id,
            tenantId=tenant_id,
            windFarmId=wind_farm_id,
            turbineId=linked_mission.turbine_id if linked_mission is not None else None,
            missionId=decision.mission_id,
            status=decision.status,
            recommendedAlternativeId=decision.recommended_alternative_id,
            recommendationReason=decision.recommendation_reason,
            alternativesJson=_json(decision.alternatives),
            risksJson=_json(decision.risks),
            source="postgresql",
            createdAt=_iso(decision.created_at),
            updatedAt=_iso(decision.updated_at),
        )
        if linked_mission is not None:
            builder.relationship(
                RelationshipType.HAS_DECISION,
                linked_mission.mission_uid,
                decision_uid,
            )

    work_order_context = _BudgetedDict[str, _WorkOrderContext](budget)
    work_order_by_mission = _BudgetedDict[str, _WorkOrderContext](budget)
    async for work_order in _iter_bounded_scalar_rows(
        session,
        select(WorkOrder).order_by(WorkOrder.id),
        budget=budget,
        key_column=WorkOrder.id,
        key_attribute="id",
    ):
        tenant_id, wind_farm_id = turbine_scope.get(work_order.turbine_id, (None, None))
        work_order_uid = builder.node(
            NodeType.WORK_ORDER,
            work_order.id,
            tenantId=tenant_id,
            windFarmId=wind_farm_id,
            missionId=work_order.mission_id,
            turbineId=work_order.turbine_id,
            title=work_order.title,
            status=work_order.status,
            priority=work_order.priority,
            assignedTeam=work_order.assigned_team,
            source="postgresql",
            createdAt=_iso(work_order.created_at),
            completedAt=_iso(work_order.completed_at),
        )
        work_order_context_value = _WorkOrderContext(
            work_order_uid,
            work_order.turbine_id,
            work_order.mission_id,
        )
        work_order_context[work_order.id] = work_order_context_value
        work_order_by_mission[work_order.mission_id] = work_order_context_value
        linked_mission = mission_context.get(work_order.mission_id)
        if linked_mission is not None:
            builder.relationship(
                RelationshipType.HAS_WORK_ORDER,
                linked_mission.mission_uid,
                work_order_uid,
            )
            if linked_mission.failure_uid is not None:
                builder.relationship(
                    RelationshipType.RESOLVED_BY,
                    linked_mission.failure_uid,
                    work_order_uid,
                )

    task_context = _BudgetedDict[str, _TaskContext](budget)
    async for task in _iter_bounded_scalar_rows(
        session,
        select(WorkOrderTask).order_by(WorkOrderTask.id),
        budget=budget,
        key_column=WorkOrderTask.id,
        key_attribute="id",
    ):
        linked_work_order = work_order_context.get(task.work_order_id)
        tenant_id, wind_farm_id = (
            turbine_scope.get(linked_work_order.turbine_id, (None, None))
            if linked_work_order is not None
            else (None, None)
        )
        procedure_uid = builder.node(
            NodeType.PROCEDURE,
            task.id,
            tenantId=tenant_id,
            windFarmId=wind_farm_id,
            turbineId=linked_work_order.turbine_id if linked_work_order is not None else None,
            workOrderId=task.work_order_id,
            sequence=task.sequence,
            title=task.title,
            status=task.status,
            result=task.result,
            completedBy=task.completed_by,
            completedAt=_iso(task.completed_at),
            source="postgresql-work-order-task",
        )
        task_context[task.id] = _TaskContext(task.work_order_id)
        if linked_work_order is not None:
            builder.relationship(
                RelationshipType.HAS_PROCEDURE,
                linked_work_order.work_order_uid,
                procedure_uid,
            )

    async for item in _iter_bounded_scalar_rows(
        session,
        select(FieldTaskEvidence).order_by(FieldTaskEvidence.id),
        budget=budget,
        key_column=FieldTaskEvidence.id,
        key_attribute="id",
    ):
        linked_task = task_context.get(item.task_id)
        linked_work_order = (
            work_order_context.get(linked_task.work_order_id) if linked_task is not None else None
        )
        tenant_id, wind_farm_id = (
            turbine_scope.get(linked_work_order.turbine_id, (None, None))
            if linked_work_order is not None
            else (None, None)
        )
        evidence_id = f"FIELD:{item.id}"
        evidence_uid = builder.node(
            NodeType.EVIDENCE,
            evidence_id,
            tenantId=tenant_id,
            windFarmId=wind_farm_id,
            turbineId=linked_work_order.turbine_id if linked_work_order is not None else None,
            taskId=item.task_id,
            evidenceType="field-task-evidence",
            summary="Verified field task evidence",
            artifactUri=item.artifact_uri,
            artifactSha256=item.artifact_sha256,
            measurementJson=_json(item.measurement),
            verifiedBy=item.verified_by,
            source="postgresql-field-evidence",
            createdAt=_iso(item.verified_at),
        )
        if linked_task is not None:
            procedure_uid = graph_uid(NodeType.PROCEDURE, item.task_id)
            builder.relationship(RelationshipType.SUPPORTED_BY, procedure_uid, evidence_uid)
            if linked_work_order is not None:
                linked_mission = mission_context.get(linked_work_order.mission_id)
                if linked_mission is not None and linked_mission.failure_uid is not None:
                    builder.relationship(
                        RelationshipType.SUPPORTED_BY,
                        linked_mission.failure_uid,
                        evidence_uid,
                        qualifier=evidence_id,
                        evidenceId=evidence_id,
                        source="verified-field-task",
                        observedAt=_iso(item.verified_at),
                        stance="supporting",
                    )

    task_context.release()
    work_order_context.release()

    resource_scope_values = _BudgetedDict[
        str, frozenset[tuple[str | None, str | None, str | None]]
    ](budget)
    async for reservation in _iter_bounded_scalar_rows(
        session,
        select(ResourceReservation).order_by(ResourceReservation.id),
        budget=budget,
        key_column=ResourceReservation.id,
        key_attribute="id",
    ):
        reserved_work_order = work_order_by_mission.get(reservation.mission_id)
        if reserved_work_order is not None:
            tenant_id, wind_farm_id = turbine_scope.get(
                reserved_work_order.turbine_id, (None, None)
            )
            scopes = resource_scope_values.get(reservation.resource_id, frozenset())
            resource_scope_values[reservation.resource_id] = scopes | frozenset(
                {(tenant_id, wind_farm_id, reserved_work_order.turbine_id)}
            )

    resource_context = _BudgetedDict[str, _ResourceContext](budget)
    async for resource in _iter_bounded_scalar_rows(
        session,
        select(Resource).order_by(Resource.id),
        budget=budget,
        key_column=Resource.id,
        key_attribute="id",
    ):
        scopes = resource_scope_values.get(resource.id, frozenset())
        tenant_ids = {scope[0] for scope in scopes if scope[0] is not None}
        wind_farm_ids = {scope[1] for scope in scopes if scope[1] is not None}
        turbine_ids = {scope[2] for scope in scopes if scope[2] is not None}
        node_type = NodeType.PART if resource.resource_type == "spare_part" else NodeType.RESOURCE
        resource_uid = builder.node(
            node_type,
            resource.id,
            tenantId=next(iter(tenant_ids)) if len(tenant_ids) == 1 else None,
            windFarmId=next(iter(wind_farm_ids)) if len(wind_farm_ids) == 1 else None,
            turbineId=next(iter(turbine_ids)) if len(turbine_ids) == 1 else None,
            resourceType=resource.resource_type,
            name=resource.name,
            quantity=resource.quantity,
            status=resource.status,
            source="postgresql",
        )
        resource_context[resource.id] = _ResourceContext(
            resource_uid=resource_uid,
            resource_type=resource.resource_type,
        )

    resource_scope_values.release()

    # A second bounded pass emits relationships after resource nodes exist. It
    # intentionally trades bounded database reads for eliminating the complete
    # in-memory reservation list that previously lived through serialization.
    async for reservation in _iter_bounded_scalar_rows(
        session,
        select(ResourceReservation).order_by(ResourceReservation.id),
        budget=budget,
        key_column=ResourceReservation.id,
        key_attribute="id",
    ):
        reserved_work_order = work_order_by_mission.get(reservation.mission_id)
        reserved_resource = resource_context.get(reservation.resource_id)
        if reserved_work_order is None or reserved_resource is None:
            continue
        relationship_type = (
            RelationshipType.REQUIRES_PART
            if reserved_resource.resource_type == "spare_part"
            else RelationshipType.EXECUTED_BY
            if reserved_resource.resource_type == "crew"
            else RelationshipType.ASSIGNED_TO
        )
        builder.relationship(
            relationship_type,
            reserved_work_order.work_order_uid,
            reserved_resource.resource_uid,
            quantity=reservation.quantity,
            source="postgresql-resource-reservation",
            createdAt=_iso(reservation.created_at),
        )

    resource_context.release()

    async for case in _iter_bounded_scalar_rows(
        session,
        select(KnowledgeCase).order_by(KnowledgeCase.id),
        budget=budget,
        key_column=KnowledgeCase.id,
        key_attribute="id",
    ):
        tenant_id, wind_farm_id = turbine_scope.get(case.turbine_id, (None, None))
        case_uid = builder.node(
            NodeType.KNOWLEDGE_CASE,
            case.id,
            tenantId=tenant_id,
            windFarmId=wind_farm_id,
            missionId=case.mission_id,
            workOrderId=case.work_order_id,
            turbineId=case.turbine_id,
            title=case.title,
            diagnosisJson=_json(case.diagnosis),
            resolutionJson=_json(case.resolution),
            source="postgresql",
            createdAt=_iso(case.created_at),
        )
        linked_turbine_uid = turbine_uids.get(case.turbine_id)
        if linked_turbine_uid is not None:
            builder.relationship(RelationshipType.RECORDED_FOR, case_uid, linked_turbine_uid)
        linked_work_order = work_order_by_mission.get(case.mission_id)
        if linked_work_order is not None:
            builder.relationship(
                RelationshipType.RESOLVED_BY,
                case_uid,
                linked_work_order.work_order_uid,
            )
        linked_mission = mission_context.get(case.mission_id)
        if linked_mission is not None and linked_mission.failure_uid is not None:
            builder.relationship(
                RelationshipType.SIMILAR_TO,
                linked_mission.failure_uid,
                case_uid,
                source="closed-loop-knowledge-case",
                confidence=float(case.diagnosis.get("confidence", 1.0)),
            )

    work_order_by_mission.release()
    mission_context.release()
    turbine_uids.release()
    turbine_scope.release()
    return builder.snapshot(projection_sequence)
