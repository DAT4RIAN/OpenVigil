from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast

from windops_backend.benchmarks.care.contract import DATASET_ID, DATASET_VERSION

REPLAY_CONTRACT_VERSION = "care-v6-replay-contract-v1"
TIME_RULE_VERSION = "care-v6-fixed-10m-window-relative-v1"
SEQUENCE_RULE_VERSION = "care-v6-source-row-sequence-v1"
SOURCE_EVENT_ID_RULE_VERSION = "care-v6-source-event-id-v1"
SOURCE_EVENT_DATASET_PREFIX = "care6"
CARE_REPLAY_SOURCE_ID = "care-v6-replay"
SYNTHETIC_TIME_CLAIM = "synthetic-replay-time-not-field-time"
SYNTHETIC_INTERVAL = timedelta(minutes=10)
MAX_SOURCE_EVENT_ID_LENGTH = 128
MAX_ONLINE_TURBINE_ID_LENGTH = 32
MAX_INGEST_BATCH_SIZE = 1000
MAX_CUSTOM_QUERY_SPAN = timedelta(days=365) - timedelta(seconds=2)
REPLAY_RUN_ID_PATTERN = re.compile(r"^[a-z0-9]{8}$")
FARMS = frozenset({"A", "B", "C"})
RUN_STATUSES = frozenset({"pending", "running", "cancelling", "cancelled", "completed", "failed"})
TERMINAL_RUN_STATUSES = frozenset({"cancelled", "completed", "failed"})


class CareReplayError(ValueError):
    """Raised when a replay would violate the frozen CARE isolation contract."""


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _require_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CareReplayError(f"{field} must include an explicit timezone")
    normalized = value.astimezone(UTC)
    if value.utcoffset() != timedelta(0):
        raise CareReplayError(f"{field} must be normalized to UTC")
    return normalized


def _require_non_empty(value: str, *, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise CareReplayError(f"{field} cannot be empty")
    return normalized


def _asset_token(source_asset_id: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]", "", source_asset_id).upper()
    if normalized and len(normalized) <= 6:
        return normalized
    return f"X{hashlib.sha256(source_asset_id.encode('utf-8')).hexdigest()[:5].upper()}"


def logical_asset_id(farm: str, source_asset_id: str) -> str:
    if farm not in FARMS:
        raise CareReplayError(f"unsupported CARE farm {farm!r}")
    source_asset_id = _require_non_empty(source_asset_id, field="source_asset_id")
    return f"CARE-{farm}-{source_asset_id}"


def online_turbine_id(
    benchmark_replay_run_id: str,
    farm: str,
    source_asset_id: str,
    event_id: int,
) -> str:
    if REPLAY_RUN_ID_PATTERN.fullmatch(benchmark_replay_run_id) is None:
        raise CareReplayError(
            "benchmark_replay_run_id must be exactly eight lowercase alphanumerics"
        )
    if farm not in FARMS:
        raise CareReplayError(f"unsupported CARE farm {farm!r}")
    if not 0 <= event_id <= 94:
        raise CareReplayError("event_id must be in the CARE v6 range 0..94")
    value = (
        f"CR6-{benchmark_replay_run_id.upper()}-{farm}{_asset_token(source_asset_id)}-E{event_id}"
    )
    if len(value) > MAX_ONLINE_TURBINE_ID_LENGTH:  # pragma: no cover - formula is bounded
        raise CareReplayError(f"online turbine ID exceeds {MAX_ONLINE_TURBINE_ID_LENGTH} chars")
    return value


@dataclass(frozen=True, slots=True)
class ReplayVariable:
    canonical_variable: str
    unit: str
    statistic: str = "average"
    short_id: str = ""

    def __post_init__(self) -> None:
        variable = _require_non_empty(self.canonical_variable, field="canonical_variable")
        unit = _require_non_empty(self.unit, field="unit")
        if len(variable) > 96:
            raise CareReplayError("canonical_variable exceeds the SCADA 96-character limit")
        if len(unit) > 24:
            raise CareReplayError("unit exceeds the SCADA 24-character limit")
        if self.statistic != "average":
            raise CareReplayError(
                "the first CARE replay contract only permits selected Avg signals"
            )
        expected = self.stable_short_id(variable)
        if self.short_id and self.short_id != expected:
            raise CareReplayError(
                f"variable short_id mismatch for {variable}: expected {expected}, "
                f"got {self.short_id}"
            )
        object.__setattr__(self, "canonical_variable", variable)
        object.__setattr__(self, "unit", unit)
        object.__setattr__(self, "short_id", expected)

    @staticmethod
    def stable_short_id(canonical_variable: str) -> str:
        return f"v{hashlib.sha256(canonical_variable.encode('utf-8')).hexdigest()[:11]}"

    def to_document(self) -> dict[str, str]:
        return {
            "short_id": self.short_id,
            "canonical_variable": self.canonical_variable,
            "statistic": self.statistic,
            "unit": self.unit,
        }


@dataclass(frozen=True, slots=True)
class ReplayCheckpoint:
    benchmark_replay_run_id: str
    last_confirmed_rows: tuple[tuple[str, int], ...]
    revision: int = 0

    def __post_init__(self) -> None:
        if REPLAY_RUN_ID_PATTERN.fullmatch(self.benchmark_replay_run_id) is None:
            raise CareReplayError("checkpoint has an invalid replay run ID")
        if self.revision < 0:
            raise CareReplayError("checkpoint revision cannot be negative")
        variable_ids = [variable_id for variable_id, _row_id in self.last_confirmed_rows]
        if variable_ids != sorted(variable_ids) or len(variable_ids) != len(set(variable_ids)):
            raise CareReplayError("checkpoint variable entries must be unique and sorted")

    def row_for(self, variable_short_id: str) -> int:
        try:
            return dict(self.last_confirmed_rows)[variable_short_id]
        except KeyError as exc:
            raise CareReplayError(
                f"checkpoint does not contain variable {variable_short_id}"
            ) from exc

    def to_document(self) -> dict[str, Any]:
        return {
            "benchmark_replay_run_id": self.benchmark_replay_run_id,
            "revision": self.revision,
            "last_confirmed_rows": dict(self.last_confirmed_rows),
        }

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> ReplayCheckpoint:
        raw_rows = value.get("last_confirmed_rows")
        if not isinstance(raw_rows, Mapping):
            raise CareReplayError("checkpoint document is missing last_confirmed_rows")
        if not all(isinstance(key, str) and isinstance(row, int) for key, row in raw_rows.items()):
            raise CareReplayError("checkpoint rows must map variable IDs to integer source rows")
        run_id = value.get("benchmark_replay_run_id")
        revision = value.get("revision")
        if not isinstance(run_id, str) or not isinstance(revision, int):
            raise CareReplayError("checkpoint document has invalid identity or revision")
        return cls(run_id, tuple(sorted(cast(Mapping[str, int], raw_rows).items())), revision)


ReplayMode = Literal["live-relative", "historical-fixed"]
ReplayStatus = Literal["pending", "running", "cancelling", "cancelled", "completed", "failed"]


@dataclass(frozen=True, slots=True)
class BenchmarkReplayRun:
    benchmark_replay_run_id: str
    farm: str
    event_id: int
    source_asset_id: str
    logical_asset_id: str
    online_turbine_id: str
    replay_mode: ReplayMode
    speed: float
    status: ReplayStatus
    replay_anchor_at: datetime
    selected_variables: tuple[ReplayVariable, ...]
    window_start_row_id: int
    window_end_row_id: int
    checkpoint: ReplayCheckpoint
    created_by: str
    created_at: datetime
    dataset_id: str = DATASET_ID
    dataset_version: str = DATASET_VERSION
    time_rule_version: str = TIME_RULE_VERSION
    sequence_rule_version: str = SEQUENCE_RULE_VERSION
    source_event_id_rule_version: str = SOURCE_EVENT_ID_RULE_VERSION
    model_id: str | None = None
    deployment_id: str | None = None
    threshold_policy_id: str | None = None
    cancelled_by: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if self.dataset_id != DATASET_ID or self.dataset_version != DATASET_VERSION:
            raise CareReplayError("BenchmarkReplayRun is restricted to the frozen CARE v6 dataset")
        if self.farm not in FARMS or not 0 <= self.event_id <= 94:
            raise CareReplayError("BenchmarkReplayRun has an invalid CARE farm/event identity")
        if REPLAY_RUN_ID_PATTERN.fullmatch(self.benchmark_replay_run_id) is None:
            raise CareReplayError(
                "benchmark_replay_run_id must be exactly eight lowercase alphanumerics"
            )
        expected_logical = logical_asset_id(self.farm, self.source_asset_id)
        expected_online = online_turbine_id(
            self.benchmark_replay_run_id,
            self.farm,
            self.source_asset_id,
            self.event_id,
        )
        if self.logical_asset_id != expected_logical or self.online_turbine_id != expected_online:
            raise CareReplayError(
                "replay logical/online asset identity does not match its run and event"
            )
        if self.replay_mode not in {"live-relative", "historical-fixed"}:
            raise CareReplayError(f"unsupported replay mode {self.replay_mode!r}")
        if not math.isfinite(self.speed) or self.speed <= 0:
            raise CareReplayError("replay speed must be finite and greater than zero")
        if self.status not in RUN_STATUSES:
            raise CareReplayError(f"unsupported replay status {self.status!r}")
        _require_utc(self.replay_anchor_at, field="replay_anchor_at")
        _require_utc(self.created_at, field="created_at")
        for field_name, value in (
            ("started_at", self.started_at),
            ("finished_at", self.finished_at),
        ):
            if value is not None:
                _require_utc(value, field=field_name)
        _require_non_empty(self.created_by, field="created_by")
        if self.window_start_row_id < 0 or self.window_end_row_id < self.window_start_row_id:
            raise CareReplayError("replay row window must be a non-negative inclusive interval")
        if (
            SYNTHETIC_INTERVAL * (self.window_end_row_id - self.window_start_row_id)
            > MAX_CUSTOM_QUERY_SPAN
        ):
            raise CareReplayError("replay window exceeds the platform's 365-day query boundary")
        if not self.selected_variables:
            raise CareReplayError("replay must select at least one Avg variable")
        variable_names = [item.canonical_variable for item in self.selected_variables]
        variable_ids = [item.short_id for item in self.selected_variables]
        if len(variable_names) != len(set(variable_names)) or len(variable_ids) != len(
            set(variable_ids)
        ):
            raise CareReplayError("replay variable names and short IDs must be unique")
        if variable_ids != sorted(variable_ids):
            raise CareReplayError("selected replay variables must be ordered by stable short ID")
        if self.time_rule_version != TIME_RULE_VERSION:
            raise CareReplayError("unknown replay time rule version")
        if self.sequence_rule_version != SEQUENCE_RULE_VERSION:
            raise CareReplayError("unknown replay sequence rule version")
        if self.source_event_id_rule_version != SOURCE_EVENT_ID_RULE_VERSION:
            raise CareReplayError("unknown replay source-event rule version")
        if self.checkpoint.benchmark_replay_run_id != self.benchmark_replay_run_id:
            raise CareReplayError("checkpoint belongs to another replay run")
        expected_checkpoint_ids = sorted(variable_ids)
        actual_checkpoint_ids = [item[0] for item in self.checkpoint.last_confirmed_rows]
        if actual_checkpoint_ids != expected_checkpoint_ids:
            raise CareReplayError("checkpoint variables do not exactly match selected variables")
        for _variable_id, row_id in self.checkpoint.last_confirmed_rows:
            if not self.window_start_row_id - 1 <= row_id <= self.window_end_row_id:
                raise CareReplayError("checkpoint row lies outside the replay window")
        if self.status == "cancelled" and not self.cancelled_by:
            raise CareReplayError("cancelled replay must record cancelled_by")
        if self.status == "failed" and not self.error:
            raise CareReplayError("failed replay must record an error")
        if self.status in TERMINAL_RUN_STATUSES and self.finished_at is None:
            raise CareReplayError("terminal replay must record finished_at")
        if self.status == "completed" and any(
            row_id != self.window_end_row_id
            for _variable_id, row_id in self.checkpoint.last_confirmed_rows
        ):
            raise CareReplayError("completed replay must have a complete per-variable checkpoint")

    def variable_by_short_id(self, short_id: str) -> ReplayVariable:
        for variable in self.selected_variables:
            if variable.short_id == short_id:
                return variable
        raise CareReplayError(f"unknown replay variable short ID {short_id!r}")

    def variable_by_name(self, name: str) -> ReplayVariable:
        for variable in self.selected_variables:
            if variable.canonical_variable == name:
                return variable
        raise CareReplayError(f"variable {name!r} is not selected by this replay")

    def to_document(self) -> dict[str, Any]:
        return {
            "benchmark_replay_run_id": self.benchmark_replay_run_id,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "farm": self.farm,
            "event_id": self.event_id,
            "source_asset_id": self.source_asset_id,
            "logical_asset_id": self.logical_asset_id,
            "online_turbine_id": self.online_turbine_id,
            "replay_mode": self.replay_mode,
            "speed": self.speed,
            "status": self.status,
            "replay_anchor_at": self.replay_anchor_at.isoformat(),
            "time_rule_version": self.time_rule_version,
            "sequence_rule_version": self.sequence_rule_version,
            "source_event_id_rule_version": self.source_event_id_rule_version,
            "selected_variables": [item.to_document() for item in self.selected_variables],
            "window": {
                "start_source_row_id": self.window_start_row_id,
                "end_source_row_id": self.window_end_row_id,
            },
            "model_id": self.model_id,
            "deployment_id": self.deployment_id,
            "threshold_policy_id": self.threshold_policy_id,
            "created_by": self.created_by,
            "cancelled_by": self.cancelled_by,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "error": self.error,
            "checkpoint": self.checkpoint.to_document(),
        }


def create_replay_run(
    *,
    benchmark_replay_run_id: str,
    farm: str,
    event_id: int,
    source_asset_id: str,
    replay_anchor_at: datetime,
    selected_variables: Iterable[ReplayVariable],
    window_start_row_id: int,
    window_end_row_id: int,
    created_by: str,
    created_at: datetime,
    replay_mode: ReplayMode = "live-relative",
    speed: float = 1.0,
    model_id: str | None = None,
    deployment_id: str | None = None,
    threshold_policy_id: str | None = None,
) -> BenchmarkReplayRun:
    if REPLAY_RUN_ID_PATTERN.fullmatch(benchmark_replay_run_id) is None:
        raise CareReplayError(
            "benchmark_replay_run_id must be exactly eight lowercase alphanumerics"
        )
    variables = tuple(sorted(selected_variables, key=lambda item: item.short_id))
    checkpoint = ReplayCheckpoint(
        benchmark_replay_run_id=benchmark_replay_run_id,
        last_confirmed_rows=tuple((item.short_id, window_start_row_id - 1) for item in variables),
    )
    return BenchmarkReplayRun(
        benchmark_replay_run_id=benchmark_replay_run_id,
        farm=farm,
        event_id=event_id,
        source_asset_id=source_asset_id,
        logical_asset_id=logical_asset_id(farm, source_asset_id),
        online_turbine_id=online_turbine_id(
            benchmark_replay_run_id, farm, source_asset_id, event_id
        ),
        replay_mode=replay_mode,
        speed=speed,
        status="pending",
        replay_anchor_at=_require_utc(replay_anchor_at, field="replay_anchor_at"),
        selected_variables=variables,
        window_start_row_id=window_start_row_id,
        window_end_row_id=window_end_row_id,
        checkpoint=checkpoint,
        created_by=created_by,
        created_at=_require_utc(created_at, field="created_at"),
        model_id=model_id,
        deployment_id=deployment_id,
        threshold_policy_id=threshold_policy_id,
    )


def validate_replay_run_registry(
    runs: Iterable[BenchmarkReplayRun],
) -> tuple[BenchmarkReplayRun, ...]:
    materialized = tuple(runs)
    run_ids = [run.benchmark_replay_run_id for run in materialized]
    online_ids = [run.online_turbine_id for run in materialized]
    if len(run_ids) != len(set(run_ids)):
        raise CareReplayError("a benchmark replay run ID cannot be registered more than once")
    if len(online_ids) != len(set(online_ids)):
        raise CareReplayError("an online replay turbine ID cannot be reused across runs")
    return materialized


def synthetic_observed_at(run: BenchmarkReplayRun, source_row_id: int) -> datetime:
    if not run.window_start_row_id <= source_row_id <= run.window_end_row_id:
        raise CareReplayError(f"source row {source_row_id} lies outside the replay window")
    return run.replay_anchor_at + SYNTHETIC_INTERVAL * (source_row_id - run.window_start_row_id)


@dataclass(frozen=True, slots=True)
class SourceEventIdentity:
    benchmark_replay_run_id: str
    farm: str
    event_id: int
    source_row_id: int
    variable_short_id: str


def build_source_event_id(
    run: BenchmarkReplayRun,
    source_row_id: int,
    variable: ReplayVariable,
) -> str:
    if run.variable_by_short_id(variable.short_id) != variable:
        raise CareReplayError("source event variable does not match the replay variable map")
    synthetic_observed_at(run, source_row_id)
    value = (
        f"care6:{run.benchmark_replay_run_id}:{run.farm}:{run.event_id}:"
        f"{source_row_id}:{variable.short_id}"
    )
    if len(value) > MAX_SOURCE_EVENT_ID_LENGTH:
        raise CareReplayError(f"source_event_id exceeds {MAX_SOURCE_EVENT_ID_LENGTH} chars")
    return value


def parse_source_event_id(run: BenchmarkReplayRun, value: str) -> SourceEventIdentity:
    if len(value) > MAX_SOURCE_EVENT_ID_LENGTH:
        raise CareReplayError("source_event_id exceeds the platform limit")
    parts = value.split(":")
    if len(parts) != 6 or parts[0] != "care6":
        raise CareReplayError("source_event_id does not use the frozen CARE v6 rule")
    try:
        event_id = int(parts[3])
        source_row_id = int(parts[4])
    except ValueError as exc:
        raise CareReplayError("source_event_id event and row identities must be integers") from exc
    identity = SourceEventIdentity(parts[1], parts[2], event_id, source_row_id, parts[5])
    if (
        identity.benchmark_replay_run_id != run.benchmark_replay_run_id
        or identity.farm != run.farm
        or identity.event_id != run.event_id
    ):
        raise CareReplayError("source_event_id belongs to another replay run or event")
    synthetic_observed_at(run, identity.source_row_id)
    run.variable_by_short_id(identity.variable_short_id)
    return identity


@dataclass(frozen=True, slots=True)
class ReplaySourceRow:
    source_row_id: int
    source_time_stamp: str
    anonymous_observed_at: str
    status_type_id: str
    values: tuple[tuple[str, float], ...]
    source_interval_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.source_row_id < 0:
            raise CareReplayError("source_row_id cannot be negative")
        _require_non_empty(self.source_time_stamp, field="source_time_stamp")
        _require_non_empty(self.anonymous_observed_at, field="anonymous_observed_at")
        _require_non_empty(self.status_type_id, field="status_type_id")
        names = [name for name, _value in self.values]
        if names != sorted(names) or len(names) != len(set(names)):
            raise CareReplayError("source row values must have unique, sorted variable names")
        if any(not math.isfinite(value) for _name, value in self.values):
            raise CareReplayError("replay source values must be finite")
        if self.source_interval_seconds is not None and (
            not math.isfinite(self.source_interval_seconds) or self.source_interval_seconds <= 0
        ):
            raise CareReplayError("source_interval_seconds must be finite and positive")

    def value_for(self, variable: str) -> float:
        try:
            return dict(self.values)[variable]
        except KeyError as exc:
            raise CareReplayError(f"source row is missing selected variable {variable!r}") from exc


PlatformQuality = Literal["good", "uncertain", "bad"]


def build_replay_sample(
    run: BenchmarkReplayRun,
    row: ReplaySourceRow,
    variable: ReplayVariable,
    *,
    platform_quality: PlatformQuality = "good",
    quality_code: str = "CARE_V6_RAW_PRESERVED",
    quality_rule_id: str,
    quality_mask_refs: Sequence[str] = (),
) -> dict[str, Any]:
    if platform_quality not in {"good", "uncertain", "bad"}:
        raise CareReplayError(f"unsupported platform quality {platform_quality!r}")
    _require_non_empty(quality_code, field="quality_code")
    _require_non_empty(quality_rule_id, field="quality_rule_id")
    observed_at = synthetic_observed_at(run, row.source_row_id)
    source_event_id = build_source_event_id(run, row.source_row_id, variable)
    return {
        "source_event_id": source_event_id,
        "source_sequence": row.source_row_id,
        "turbine_id": run.online_turbine_id,
        "observed_at": observed_at.isoformat(),
        "variable": variable.canonical_variable,
        "value": row.value_for(variable.canonical_variable),
        "unit": variable.unit,
        "quality": platform_quality,
        "quality_code": quality_code,
        "attributes": {
            "benchmark_replay_run_id": run.benchmark_replay_run_id,
            "dataset_id": run.dataset_id,
            "dataset_version": run.dataset_version,
            "farm": run.farm,
            "event_id": run.event_id,
            "source_asset_id": run.source_asset_id,
            "logical_asset_id": run.logical_asset_id,
            "online_turbine_id": run.online_turbine_id,
            "source_row_id": row.source_row_id,
            "source_time_stamp": row.source_time_stamp,
            "anonymous_observed_at": row.anonymous_observed_at,
            "original_interval_seconds": row.source_interval_seconds,
            "observed_at_is_synthetic": True,
            "time_claim": SYNTHETIC_TIME_CLAIM,
            "time_rule_version": run.time_rule_version,
            "sequence_rule_version": run.sequence_rule_version,
            "source_event_id_rule_version": run.source_event_id_rule_version,
            "variable_short_id": variable.short_id,
            "canonical_variable": variable.canonical_variable,
            "statistic": variable.statistic,
            "status_type_id": row.status_type_id,
            "status_is_platform_quality": False,
            "quality_rule_id": quality_rule_id,
            "quality_mask_refs": list(quality_mask_refs),
            "raw_value_preserved": True,
        },
    }


def iter_replay_batches(
    run: BenchmarkReplayRun,
    rows: Iterable[ReplaySourceRow],
    *,
    quality_rule_id: str,
    batch_size: int = MAX_INGEST_BATCH_SIZE,
) -> Iterator[tuple[dict[str, Any], ...]]:
    if not 1 <= batch_size <= MAX_INGEST_BATCH_SIZE:
        raise CareReplayError(f"batch_size must be within 1..{MAX_INGEST_BATCH_SIZE}")
    expected_row_id = run.window_start_row_id
    batch: list[dict[str, Any]] = []
    seen_rows = 0
    for row in rows:
        if row.source_row_id != expected_row_id:
            raise CareReplayError(
                f"replay rows must preserve the contiguous source IDs; expected {expected_row_id}, "
                f"got {row.source_row_id}"
            )
        expected_row_id += 1
        seen_rows += 1
        for variable in run.selected_variables:
            if row.source_row_id <= run.checkpoint.row_for(variable.short_id):
                continue
            batch.append(
                build_replay_sample(
                    run,
                    row,
                    variable,
                    quality_rule_id=quality_rule_id,
                )
            )
            if len(batch) == batch_size:
                yield tuple(batch)
                batch.clear()
    expected_count = run.window_end_row_id - run.window_start_row_id + 1
    if seen_rows != expected_count or expected_row_id - 1 != run.window_end_row_id:
        raise CareReplayError("replay rows do not exactly cover the configured inclusive window")
    if batch:
        yield tuple(batch)


def replay_ingest_request(samples: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not 1 <= len(samples) <= MAX_INGEST_BATCH_SIZE:
        raise CareReplayError("ingest request must contain between 1 and 1000 replay samples")
    validate_replay_window(samples)
    return {"source_id": CARE_REPLAY_SOURCE_ID, "samples": [dict(item) for item in samples]}


def advance_checkpoint(
    run: BenchmarkReplayRun,
    confirmed_samples: Iterable[Mapping[str, Any]],
) -> BenchmarkReplayRun:
    confirmed: dict[str, set[int]] = defaultdict(set)
    for sample in confirmed_samples:
        source_event_id = sample.get("source_event_id")
        if not isinstance(source_event_id, str):
            raise CareReplayError("confirmed sample is missing source_event_id")
        identity = parse_source_event_id(run, source_event_id)
        if sample.get("turbine_id") != run.online_turbine_id:
            raise CareReplayError("confirmed sample belongs to another online replay instance")
        if sample.get("source_sequence") != identity.source_row_id:
            raise CareReplayError("confirmed sample sequence disagrees with its source event ID")
        if (
            sample.get("variable")
            != run.variable_by_short_id(identity.variable_short_id).canonical_variable
        ):
            raise CareReplayError("confirmed sample variable disagrees with its source event ID")
        confirmed[identity.variable_short_id].add(identity.source_row_id)
    if not confirmed:
        raise CareReplayError("cannot advance a checkpoint without confirmed samples")
    updated = dict(run.checkpoint.last_confirmed_rows)
    original = dict(updated)
    for variable_id, row_ids in confirmed.items():
        current = updated[variable_id]
        new_rows = sorted(row_id for row_id in row_ids if row_id > current)
        if not new_rows:
            continue
        expected = list(range(current + 1, new_rows[-1] + 1))
        if new_rows != expected:
            raise CareReplayError(
                f"checkpoint for {variable_id} cannot advance across an unconfirmed row"
            )
        updated[variable_id] = new_rows[-1]
    if updated == original:
        return run
    checkpoint = ReplayCheckpoint(
        run.benchmark_replay_run_id,
        tuple(sorted(updated.items())),
        run.checkpoint.revision + 1,
    )
    return replace(run, checkpoint=checkpoint)


_ALLOWED_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "pending": frozenset({"running", "cancelled", "failed"}),
    "running": frozenset({"cancelling", "completed", "failed"}),
    "cancelling": frozenset({"cancelled", "failed"}),
    "cancelled": frozenset(),
    "completed": frozenset(),
    "failed": frozenset(),
}


def transition_replay_run(
    run: BenchmarkReplayRun,
    target: ReplayStatus,
    *,
    at: datetime,
    actor: str | None = None,
    error: str | None = None,
) -> BenchmarkReplayRun:
    at = _require_utc(at, field="transition time")
    if target not in _ALLOWED_TRANSITIONS[run.status]:
        raise CareReplayError(f"invalid replay status transition {run.status} -> {target}")
    changes: dict[str, Any] = {"status": target}
    if target == "running":
        changes["started_at"] = at
    if target == "cancelling":
        changes["cancelled_by"] = _require_non_empty(actor or "", field="cancelling actor")
    if target == "cancelled":
        changes["cancelled_by"] = _require_non_empty(
            actor or run.cancelled_by or "", field="cancelled_by"
        )
        changes["finished_at"] = at
    if target == "failed":
        changes["error"] = _require_non_empty(error or "", field="replay error")
        changes["finished_at"] = at
    if target == "completed":
        changes["finished_at"] = at
    return replace(run, **changes)


@dataclass(frozen=True, slots=True)
class ReplayWindowIdentity:
    benchmark_replay_run_id: str
    dataset_version: str
    farm: str
    event_id: int
    online_turbine_id: str


def validate_replay_window(samples: Iterable[Mapping[str, Any]]) -> ReplayWindowIdentity:
    identities: set[ReplayWindowIdentity] = set()
    count = 0
    for sample in samples:
        count += 1
        attributes = sample.get("attributes")
        if not isinstance(attributes, Mapping):
            raise CareReplayError("replay sample is missing governed attributes")
        try:
            identity = ReplayWindowIdentity(
                benchmark_replay_run_id=str(attributes["benchmark_replay_run_id"]),
                dataset_version=str(attributes["dataset_version"]),
                farm=str(attributes["farm"]),
                event_id=int(attributes["event_id"]),
                online_turbine_id=str(sample["turbine_id"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CareReplayError("replay sample has an incomplete window identity") from exc
        if attributes.get("online_turbine_id") != identity.online_turbine_id:
            raise CareReplayError("sample and attribute online replay identities disagree")
        if identity.dataset_version != DATASET_VERSION or identity.farm not in FARMS:
            raise CareReplayError("replay sample has an unsupported dataset or farm identity")
        if attributes.get("observed_at_is_synthetic") is not True:
            raise CareReplayError("replay sample does not identify its observed_at as synthetic")
        if attributes.get("time_claim") != SYNTHETIC_TIME_CLAIM:
            raise CareReplayError("replay sample does not carry the synthetic-time claim")
        source_event_id = sample.get("source_event_id")
        if (
            not isinstance(source_event_id, str)
            or len(source_event_id) > MAX_SOURCE_EVENT_ID_LENGTH
        ):
            raise CareReplayError("replay sample has an invalid source_event_id")
        parts = source_event_id.split(":")
        try:
            event_id = int(parts[3])
            source_row_id = int(parts[4])
        except (IndexError, ValueError) as exc:
            raise CareReplayError("replay sample has an invalid source_event_id") from exc
        if (
            len(parts) != 6
            or parts[0] != "care6"
            or parts[1] != identity.benchmark_replay_run_id
            or parts[2] != identity.farm
            or event_id != identity.event_id
            or sample.get("source_sequence") != source_row_id
            or attributes.get("source_row_id") != source_row_id
            or attributes.get("variable_short_id") != parts[5]
        ):
            raise CareReplayError("replay sample identity fields disagree")
        identities.add(identity)
    if count == 0:
        raise CareReplayError("replay/model window cannot be empty")
    if len(identities) != 1:
        raise CareReplayError("replay/model window cannot cross an event or replay run")
    return next(iter(identities))


@dataclass(frozen=True, slots=True)
class ReplayQueryPlan:
    range_name: Literal["LIVE", "24H", "30D", "CUSTOM"]
    starts_at: datetime
    ends_at: datetime
    observed_at_is_synthetic: bool = True
    time_claim: str = SYNTHETIC_TIME_CLAIM
    time_rule_version: str = TIME_RULE_VERSION

    def contains(self, observed_at: datetime) -> bool:
        observed_at = _require_utc(observed_at, field="observed_at")
        return self.starts_at <= observed_at <= self.ends_at


def choose_query_plan(run: BenchmarkReplayRun, *, reference_at: datetime) -> ReplayQueryPlan:
    reference_at = _require_utc(reference_at, field="reference_at")
    starts_at = synthetic_observed_at(run, run.window_start_row_id)
    ends_at = synthetic_observed_at(run, run.window_end_row_id)
    if ends_at > reference_at:
        raise CareReplayError("synthetic replay time extends into the future at query time")
    for range_name, duration in (
        ("LIVE", timedelta(minutes=15)),
        ("24H", timedelta(hours=24)),
        ("30D", timedelta(days=30)),
    ):
        if starts_at >= reference_at - duration:
            return ReplayQueryPlan(cast(Any, range_name), starts_at, reference_at)
    return ReplayQueryPlan(
        "CUSTOM",
        starts_at - timedelta(seconds=1),
        ends_at + timedelta(seconds=1),
    )


def build_replay_contract() -> dict[str, Any]:
    contract: dict[str, Any] = {
        "schema_version": REPLAY_CONTRACT_VERSION,
        "dataset": {"id": DATASET_ID, "version": DATASET_VERSION},
        "source": {
            "source_id": CARE_REPLAY_SOURCE_ID,
            "maximum_ingest_batch_size": MAX_INGEST_BATCH_SIZE,
            "governance": "preconfigured-source-policy",
        },
        "asset_identity": {
            "logical": "CARE-<farm>-<source_asset>",
            "online": "CR6-<run8>-<farm><asset-token>-E<event>",
            "online_max_length": MAX_ONLINE_TURBINE_ID_LENGTH,
            "online_scope": ["benchmark_replay_run_id", "event_id"],
            "reuse_across_runs": False,
        },
        "benchmark_replay_run": {
            "immutable_identity_fields": [
                "benchmark_replay_run_id",
                "dataset_id",
                "dataset_version",
                "farm",
                "event_id",
                "source_asset_id",
                "logical_asset_id",
                "online_turbine_id",
                "replay_anchor_at",
                "time_rule_version",
                "sequence_rule_version",
                "source_event_id_rule_version",
                "selected_variables",
                "window",
            ],
            "statuses": sorted(RUN_STATUSES),
            "terminal_statuses": sorted(TERMINAL_RUN_STATUSES),
            "checkpoint_scope": "per-variable-stable-short-id",
            "checkpoint_advance": "contiguous-confirmed-source-rows-only",
        },
        "time_rule": {
            "version": TIME_RULE_VERSION,
            "expression": ("replay_anchor_at + (source_row_id - window_start_row_id) * 10 minutes"),
            "anchor_semantics": "synthetic observed_at of the first selected source row",
            "anchor_immutable_after_create": True,
            "interval_seconds": int(SYNTHETIC_INTERVAL.total_seconds()),
            "claim": SYNTHETIC_TIME_CLAIM,
            "preserved": [
                "source_time_stamp",
                "anonymous_observed_at",
                "original_interval_seconds",
                "source_row_id",
            ],
            "query_ranges": ["LIVE", "24H", "30D", "CUSTOM"],
            "maximum_custom_query_span_seconds": int(
                (MAX_CUSTOM_QUERY_SPAN + timedelta(seconds=2)).total_seconds()
            ),
        },
        "sequence_rule": {
            "version": SEQUENCE_RULE_VERSION,
            "source_sequence": "unmodified source_row_id",
            "watermark_scope": ["source_id", "online_turbine_id", "variable"],
            "window_rows_are_not_renumbered": True,
        },
        "source_event_id_rule": {
            "version": SOURCE_EVENT_ID_RULE_VERSION,
            "format": "care6:<run8>:<farm>:<event>:<source-row>:<variable-short-id>",
            "dataset_version_token": SOURCE_EVENT_DATASET_PREFIX,
            "maximum_length": MAX_SOURCE_EVENT_ID_LENGTH,
            "variable_identity": "v + first 11 sha256 hex of canonical variable",
            "variable_map_required_for_reversal": True,
        },
        "idempotency": {
            "same_run_same_step": "same source_event_id and payload; receipt duplicate",
            "same_key_different_payload": "conflict",
            "new_run": "new run ID, online turbine ID, stream, and source_event_id namespace",
        },
        "data_semantics": {
            "selected_statistics": ["average"],
            "status_type_id_is_platform_quality": False,
            "raw_value_preserved": True,
            "quality_rules_and_masks_are_attributes": True,
            "model_windows_must_match": [
                "dataset_version",
                "farm",
                "event_id",
                "benchmark_replay_run_id",
                "online_turbine_id",
            ],
        },
        "phase_boundaries": {
            "database_entities_and_migration": "CARE-H002",
            "actual_two-event_platform_replay": "CARE-H005",
        },
    }
    contract["contract_sha256"] = _sha256_json(contract)
    return contract


def verify_replay_contract(contract: Mapping[str, Any]) -> None:
    actual_hash = contract.get("contract_sha256")
    if not isinstance(actual_hash, str):
        raise CareReplayError("replay contract is missing contract_sha256")
    unsigned = {key: value for key, value in contract.items() if key != "contract_sha256"}
    expected_hash = _sha256_json(unsigned)
    if actual_hash != expected_hash:
        raise CareReplayError(
            f"replay contract hash mismatch: expected {expected_hash}, got {actual_hash}"
        )
    expected = build_replay_contract()
    if dict(contract) != expected:
        raise CareReplayError("replay contract semantics differ from the frozen implementation")


def write_replay_contract(path: Path, contract: Mapping[str, Any] | None = None) -> None:
    document = dict(contract or build_replay_contract())
    verify_replay_contract(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write the immutable CARE v6 replay contract")
    parser.add_argument("output", type=Path, help="Project-local replay contract JSON path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    write_replay_contract(args.output)
    return 0
