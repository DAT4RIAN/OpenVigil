from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from windops_backend.benchmarks.care.contract import (
    DATASET_ID,
    DATASET_VERSION,
    METADATA_COLUMNS,
    CareContractError,
    verify_care_contract,
)

QUALITY_CONTRACT_VERSION = "care-v6-quality-contract-v1"
QUALITY_RULE_VERSION = "care-v6-quality-rules-v1"
FEATURE_SET_VERSION = "care-v6-avg-feature-set-v1"
STATUS_RULE_VERSION = "care-v6-status-rules-v1"
STATUS_CORROBORATION_RULE_ID = "care-v6-bc-status-signal-corroboration-v1"
STATUS_SUSTAINED_DISAGREEMENT_MIN_ROWS = 3
STATUS_SIGNAL_ZERO_TOLERANCE = 1e-12
UNIT_RULE_VERSION = "care-v6-unit-rules-v1"
TIME_RULE_VERSION = "care-v6-anonymous-time-v1"
ZERO_RUN_RULE_ID = "care-v6-bc-prolonged-zero-v1"
DEFAULT_ZERO_RUN_MIN_LENGTH = 6

POWER_UNITS = {"W", "kW", "MW", "VAr", "kVAr", "var", "kvar", "kVA", "%"}
UNIT_REPAIRS = {
    "�C": ("°C", "repair-mojibake-celsius"),
    "�": ("°", "repair-mojibake-degree"),
    "Celsius": ("°C", "normalize-celsius"),
    "deg": ("°", "normalize-degree"),
}


@dataclass(frozen=True)
class UnitSemantics:
    source_unit: str
    normalized_unit: str
    rule_id: str
    rule_version: str = UNIT_RULE_VERSION


@dataclass(frozen=True)
class StatusDecision:
    model_usable: bool
    reason: str
    confidence: float
    rule_version: str = STATUS_RULE_VERSION


@dataclass(frozen=True, slots=True)
class StatusPointEvidence:
    disagreement_run_length: int
    corroborated_by_signal: bool
    corroboration_signal_count: int
    corroboration_finite_signal_count: int
    corroboration_inactive_or_invalid_signal_count: int
    corroboration_rule_id: str = STATUS_CORROBORATION_RULE_ID


@dataclass(slots=True)
class StatusSequenceState:
    """Derive status evidence across record batches within exactly one CARE event."""

    farm: str
    trusted_status_ids: tuple[str, ...]
    _previous_source_row_id: int | None = None
    _previous_split: str | None = None
    _previous_disagreement_status_id: str | None = None
    _disagreement_run_length: int = 0

    def __post_init__(self) -> None:
        if self.farm not in {"A", "B", "C"}:
            raise CareContractError(f"unknown CARE farm for status sequence: {self.farm}")
        self.trusted_status_ids = tuple(sorted(set(self.trusted_status_ids)))
        if not self.trusted_status_ids:
            raise CareContractError("status sequence requires an explicit trusted allowlist")

    def observe(
        self,
        *,
        source_row_id: int,
        split: str,
        status_id: str,
        corroboration_signal_values: Sequence[Any],
    ) -> StatusPointEvidence:
        if (
            isinstance(source_row_id, bool)
            or not isinstance(source_row_id, int)
            or source_row_id < 0
        ):
            raise CareContractError("status sequence source row ID must be non-negative")
        if split not in {"train", "prediction"}:
            raise CareContractError(f"unknown CARE split for status sequence: {split}")
        status_id = str(status_id)
        trusted = status_id in self.trusted_status_ids
        contiguous = (
            self._previous_source_row_id is not None
            and source_row_id == self._previous_source_row_id + 1
            and split == self._previous_split
            and status_id == self._previous_disagreement_status_id
            and not trusted
        )
        self._disagreement_run_length = self._disagreement_run_length + 1 if contiguous else 1
        self._previous_source_row_id = source_row_id
        self._previous_split = split
        self._previous_disagreement_status_id = None if trusted else status_id

        finite_count = 0
        inactive_or_invalid_count = 0
        for raw_value in corroboration_signal_values:
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                inactive_or_invalid_count += 1
                continue
            if not math.isfinite(value):
                inactive_or_invalid_count += 1
                continue
            finite_count += 1
            if abs(value) <= STATUS_SIGNAL_ZERO_TOLERANCE:
                inactive_or_invalid_count += 1
        signal_count = len(corroboration_signal_values)
        corroborated = (
            self.farm in {"B", "C"}
            and not trusted
            and signal_count > 0
            and inactive_or_invalid_count == signal_count
        )
        return StatusPointEvidence(
            disagreement_run_length=self._disagreement_run_length,
            corroborated_by_signal=corroborated,
            corroboration_signal_count=signal_count,
            corroboration_finite_signal_count=finite_count,
            corroboration_inactive_or_invalid_signal_count=inactive_or_invalid_count,
        )


def status_evidence_policy(
    farm: str,
    corroboration_signal_columns: Sequence[str],
) -> dict[str, Any]:
    if farm not in {"A", "B", "C"}:
        raise CareContractError(f"unknown CARE farm for status evidence policy: {farm}")
    columns = tuple(str(value) for value in corroboration_signal_columns)
    if len(columns) != len(set(columns)) or any(not value for value in columns):
        raise CareContractError("status corroboration signal columns must be unique and non-empty")
    if farm in {"B", "C"} and not columns:
        raise CareContractError("B/C status corroboration requires approved signal columns")
    return {
        "rule_version": STATUS_RULE_VERSION,
        "corroboration_rule_id": STATUS_CORROBORATION_RULE_ID,
        "minimum_sustained_disagreement_rows": STATUS_SUSTAINED_DISAGREEMENT_MIN_ROWS,
        "zero_tolerance": STATUS_SIGNAL_ZERO_TOLERANCE,
        "corroboration_signal_columns": list(columns),
        "corroboration_predicate": (
            "all-approved-scaled-power-signals-zero-nonfinite-or-unparseable"
        ),
        "run_length_scope": ["dataset_version", "farm", "event_id", "split", "status_id"],
        "record_batch_boundary_resets_run": False,
        "noncontiguous_source_row_resets_run": True,
        "event_boundary_resets_run": True,
    }


@dataclass
class _FeatureAccumulator:
    source_column: str
    statistic: str
    is_counter: bool
    rows: int = 0
    zero_count: int = 0
    longest_zero_run: int = 0
    null_count: int = 0
    nan_count: int = 0
    positive_infinity_count: int = 0
    negative_infinity_count: int = 0
    parse_failure_count: int = 0
    finite_count: int = 0
    minimum: float | None = None
    maximum: float | None = None
    zero_by_status: Counter[str] = field(default_factory=Counter)
    zero_power_association: Counter[str] = field(default_factory=Counter)
    std_negative_count: int = 0
    min_avg_max_violation_count: int = 0
    counter_regression_count: int = 0
    previous_counter_value: float | None = None
    active_zero_start_id: int | None = None
    active_zero_end_id: int | None = None
    active_zero_length: int = 0
    active_zero_power: Counter[str] = field(default_factory=Counter)
    mask_ranges: list[dict[str, Any]] = field(default_factory=list)

    def _close_zero_run(self, *, farm: str, zero_run_min_length: int) -> None:
        if self.active_zero_length == 0:
            return
        self.longest_zero_run = max(self.longest_zero_run, self.active_zero_length)
        if farm in {"B", "C"} and self.active_zero_length >= zero_run_min_length:
            nonzero_power_rows = self.active_zero_power["nonzero"]
            confidence = 0.95 if nonzero_power_rows else 0.65
            reason = (
                "prolonged zero while a scaled power signal is nonzero"
                if nonzero_power_rows
                else "prolonged zero with uncertain or zero scaled-power context"
            )
            self.mask_ranges.append(
                {
                    "source_column": self.source_column,
                    "source_row_id_start": self.active_zero_start_id,
                    "source_row_id_end": self.active_zero_end_id,
                    "length": self.active_zero_length,
                    "rule_id": ZERO_RUN_RULE_ID,
                    "rule_version": QUALITY_RULE_VERSION,
                    "reason": reason,
                    "confidence": confidence,
                    "raw_value_preserved": True,
                    "power_context_counts": dict(sorted(self.active_zero_power.items())),
                }
            )
        self.active_zero_start_id = None
        self.active_zero_end_id = None
        self.active_zero_length = 0
        self.active_zero_power.clear()

    def observe(
        self,
        *,
        value: float | None,
        category: str,
        source_row_id: int,
        status_id: str,
        power_state: str,
        farm: str,
        zero_run_min_length: int,
    ) -> None:
        self.rows += 1
        if category == "null":
            self.null_count += 1
        elif category == "nan":
            self.nan_count += 1
        elif category == "positive-infinity":
            self.positive_infinity_count += 1
        elif category == "negative-infinity":
            self.negative_infinity_count += 1
        elif category == "parse-failure":
            self.parse_failure_count += 1

        is_zero = category == "finite" and value == 0.0
        if is_zero:
            self.zero_count += 1
            self.zero_by_status[status_id] += 1
            self.zero_power_association[power_state] += 1
            if self.active_zero_length == 0:
                self.active_zero_start_id = source_row_id
            self.active_zero_end_id = source_row_id
            self.active_zero_length += 1
            self.active_zero_power[power_state] += 1
        else:
            self._close_zero_run(farm=farm, zero_run_min_length=zero_run_min_length)

        if category != "finite" or value is None:
            return
        self.finite_count += 1
        self.minimum = value if self.minimum is None else min(self.minimum, value)
        self.maximum = value if self.maximum is None else max(self.maximum, value)
        if self.statistic == "std_dev" and value < 0:
            self.std_negative_count += 1
        if self.is_counter:
            if self.previous_counter_value is not None and value < self.previous_counter_value:
                self.counter_regression_count += 1
            self.previous_counter_value = value

    def finish(self, *, farm: str, zero_run_min_length: int) -> None:
        self._close_zero_run(farm=farm, zero_run_min_length=zero_run_min_length)

    def summary(self) -> dict[str, Any]:
        return {
            "source_column": self.source_column,
            "row_count": self.rows,
            "zero_count": self.zero_count,
            "zero_ratio": self.zero_count / self.rows if self.rows else 0.0,
            "longest_consecutive_zero_run": self.longest_zero_run,
            "zero_by_status": dict(sorted(self.zero_by_status.items())),
            "zero_power_association": dict(sorted(self.zero_power_association.items())),
            "null_count": self.null_count,
            "nan_count": self.nan_count,
            "positive_infinity_count": self.positive_infinity_count,
            "negative_infinity_count": self.negative_infinity_count,
            "parse_failure_count": self.parse_failure_count,
            "finite_count": self.finite_count,
            "constant_finite_value": self.finite_count > 0 and self.minimum == self.maximum,
            "finite_minimum": self.minimum,
            "finite_maximum": self.maximum,
            "std_negative_count": self.std_negative_count,
            "min_avg_max_violation_count": self.min_avg_max_violation_count,
            "counter_regression_or_reset_count": self.counter_regression_count,
        }


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_unit(
    source_unit: str,
    *,
    dimensionless_confirmed: bool = False,
) -> UnitSemantics:
    if source_unit in UNIT_REPAIRS:
        normalized, rule_id = UNIT_REPAIRS[source_unit]
        return UnitSemantics(source_unit, normalized, rule_id)
    if not source_unit:
        if dimensionless_confirmed:
            return UnitSemantics(source_unit, "1", "empty-confirmed-dimensionless")
        return UnitSemantics(source_unit, "unknown", "empty-unit-unresolved")
    return UnitSemantics(source_unit, source_unit, "preserve-source-unit")


def is_anonymized_scaled_power(mapping: Mapping[str, Any]) -> bool:
    if bool(mapping.get("is_counter")):
        return False
    description = str(mapping.get("description", "")).casefold()
    source_unit = normalize_unit(str(mapping.get("source_unit", ""))).normalized_unit
    return "power" in description and source_unit in POWER_UNITS


def evaluate_status_point(
    *,
    farm: str,
    split: str,
    status_id: str,
    trusted_status_ids: Sequence[str],
    disagreement_run_length: int = 1,
    corroborated_by_signal: bool = False,
) -> StatusDecision:
    if farm not in {"A", "B", "C"}:
        raise CareContractError(f"unknown CARE farm for status policy: {farm}")
    if split not in {"train", "prediction"}:
        raise CareContractError(f"unknown CARE split for status policy: {split}")
    trusted = set(trusted_status_ids)
    if not trusted:
        raise CareContractError("status policy requires an explicit trusted-status allowlist")
    if farm == "A" and split == "prediction":
        return StatusDecision(True, "care-v6-a-prediction-status-exception", 1.0)
    if status_id in trusted:
        return StatusDecision(True, "trusted-operating-status", 1.0)
    if farm == "A":
        return StatusDecision(False, "untrusted-a-train-status", 0.95)
    if (
        disagreement_run_length < STATUS_SUSTAINED_DISAGREEMENT_MIN_ROWS
        or not corroborated_by_signal
    ):
        return StatusDecision(True, "bc-short-status-disagreement-retained", 0.5)
    return StatusDecision(False, "bc-sustained-corroborated-status-disagreement", 0.9)


def _feature_semantics(mapping: Mapping[str, Any]) -> dict[str, Any]:
    unit = normalize_unit(str(mapping["source_unit"]))
    scaled_power = is_anonymized_scaled_power(mapping)
    statistic = str(mapping["statistic"])
    return {
        "source_column": mapping["source_column"],
        "base_sensor": mapping["base_sensor"],
        "statistic": statistic,
        "enabled_by_default": statistic == "average",
        "disabled_reason": None if statistic == "average" else "non-average-disabled-by-default",
        "source_unit": unit.source_unit,
        "normalized_unit": unit.normalized_unit,
        "unit_rule_id": unit.rule_id,
        "unit_rule_version": unit.rule_version,
        "value_domain": "circular" if mapping["is_angle"] else "linear",
        "is_angle": mapping["is_angle"],
        "is_counter": mapping["is_counter"],
        "counter_policy": "detect-regression-reset-and-wrap" if mapping["is_counter"] else None,
        "value_semantics": "anonymized-rated-power-scaled" if scaled_power else "source-defined",
        "absolute_power_interpretation_allowed": not scaled_power,
        "description": mapping["description"],
    }


def build_quality_contract(manifest: Mapping[str, Any]) -> dict[str, Any]:
    verify_care_contract(manifest)
    farms: list[dict[str, Any]] = []
    all_enabled: list[str] = []
    unit_rule_counts: Counter[str] = Counter()
    scaled_power_count = 0
    for farm in manifest["farms"]:
        semantics = [_feature_semantics(mapping) for mapping in farm["column_mappings"]]
        enabled = [str(item["source_column"]) for item in semantics if item["enabled_by_default"]]
        all_enabled.extend(f"{farm['farm']}:{column}" for column in enabled)
        unit_rule_counts.update(str(item["unit_rule_id"]) for item in semantics)
        scaled_power_count += sum(
            item["value_semantics"] == "anonymized-rated-power-scaled" for item in semantics
        )
        farms.append(
            {
                "farm": farm["farm"],
                "feature_count": len(semantics),
                "default_enabled_avg_count": len(enabled),
                "default_disabled_non_avg_count": len(semantics) - len(enabled),
                "feature_semantics_sha256": _canonical_hash(semantics),
                "features": semantics,
            }
        )
    payload: dict[str, Any] = {
        "quality_contract_version": QUALITY_CONTRACT_VERSION,
        "quality_rule_version": QUALITY_RULE_VERSION,
        "feature_set_version": FEATURE_SET_VERSION,
        "feature_set_sha256": _canonical_hash(sorted(all_enabled)),
        "source_manifest_sha256": manifest["manifest_sha256"],
        "dataset_id": DATASET_ID,
        "dataset_version": DATASET_VERSION,
        "raw_value_policy": "preserve; quality findings are separate masks",
        "zero_value_policy": {
            "global_zero_to_null": False,
            "bc_mask_rule_id": ZERO_RUN_RULE_ID,
            "minimum_consecutive_zero_rows": DEFAULT_ZERO_RUN_MIN_LENGTH,
            "legal_short_or_uncorroborated_zero": "preserve-unmasked",
        },
        "status_policy": {
            "rule_version": STATUS_RULE_VERSION,
            "status_is_platform_quality": False,
            "explicit_trusted_allowlist_required": True,
            "A": {
                "train": "filter-by-explicit-trusted-status",
                "prediction": "retain-all-statuses-care-v6-exception",
            },
            "B": "short-disagreement-retained; sustained corroborated disagreement may mask",
            "C": "short-disagreement-retained; sustained corroborated disagreement may mask",
        },
        "time_semantics": {
            "rule_version": TIME_RULE_VERSION,
            "source_time_stamp_preserved": True,
            "anonymous_observed_at_preserved": True,
            "source_row_id_preserved": True,
            "timestamp_semantics": "independently-shifted-anonymized",
            "cross_event_ordering_allowed": False,
            "real_site_time_claim_allowed": False,
        },
        "physical_constraint_rules": [
            "std-dev-must-be-nonnegative",
            "minimum-less-than-or-equal-average-less-than-or-equal-maximum",
            "counter-regression-reset-wrap-detected-not-rewritten",
            "angles-use-circular-domain",
        ],
        "summary": {
            "feature_mapping_count": sum(int(farm["feature_count"]) for farm in farms),
            "default_enabled_avg_count": len(all_enabled),
            "default_disabled_non_avg_count": sum(
                int(farm["default_disabled_non_avg_count"]) for farm in farms
            ),
            "scaled_power_mapping_count": scaled_power_count,
            "unit_rule_counts": dict(sorted(unit_rule_counts.items())),
        },
        "farms": farms,
    }
    return {**payload, "quality_contract_sha256": _canonical_hash(payload)}


def verify_quality_contract(quality_contract: Mapping[str, Any]) -> None:
    actual = quality_contract.get("quality_contract_sha256")
    if not isinstance(actual, str):
        raise CareContractError("CARE quality contract is missing quality_contract_sha256")
    unsigned = {
        key: value for key, value in quality_contract.items() if key != "quality_contract_sha256"
    }
    expected = _canonical_hash(unsigned)
    if actual != expected:
        raise CareContractError(
            f"CARE quality contract hash mismatch: expected {expected}, got {actual}"
        )


def _parse_value(raw: bytes) -> tuple[float | None, str]:
    value = raw.strip()
    if not value:
        return None, "null"
    lowered = value.lower()
    if lowered in {b"nan", b"+nan", b"-nan"}:
        return None, "nan"
    if lowered in {b"inf", b"+inf", b"infinity", b"+infinity"}:
        return None, "positive-infinity"
    if lowered in {b"-inf", b"-infinity"}:
        return None, "negative-infinity"
    try:
        parsed = float(value)
    except ValueError:
        return None, "parse-failure"
    if math.isnan(parsed):
        return None, "nan"
    if math.isinf(parsed):
        return None, "positive-infinity" if parsed > 0 else "negative-infinity"
    return parsed, "finite"


def _resolve_event(
    manifest: Mapping[str, Any],
    event_id: int,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    events = [event for event in manifest["events"] if int(event["event_id"]) == event_id]
    if len(events) != 1:
        raise CareContractError(f"CARE manifest must contain exactly one event {event_id}")
    event = events[0]
    farms = [farm for farm in manifest["farms"] if farm["farm"] == event["farm"]]
    if len(farms) != 1:
        raise CareContractError(f"CARE manifest farm contract missing for event {event_id}")
    return event, farms[0]


def audit_event_quality(
    manifest: Mapping[str, Any],
    quality_contract: Mapping[str, Any],
    dataset_root: Path,
    event_id: int,
    *,
    zero_run_min_length: int = DEFAULT_ZERO_RUN_MIN_LENGTH,
) -> dict[str, Any]:
    verify_care_contract(manifest)
    verify_quality_contract(quality_contract)
    if quality_contract.get("source_manifest_sha256") != manifest["manifest_sha256"]:
        raise CareContractError("quality contract does not belong to the CARE manifest")
    if zero_run_min_length < 2:
        raise CareContractError("zero-run minimum must be at least 2")
    event, farm_contract = _resolve_event(manifest, event_id)
    farm = str(event["farm"])
    quality_farms = [item for item in quality_contract["farms"] if item["farm"] == farm]
    if len(quality_farms) != 1:
        raise CareContractError(f"quality contract is missing farm {farm}")
    semantics = quality_farms[0]["features"]
    root = dataset_root.resolve()
    event_path = (root / str(event["relative_path"])).resolve()
    if not event_path.is_relative_to(root) or not event_path.is_file():
        raise CareContractError("event path escapes or is absent from the read-only CARE root")

    expected_header = (*METADATA_COLUMNS, *(item["source_column"] for item in semantics))
    accumulators = [
        _FeatureAccumulator(
            source_column=str(item["source_column"]),
            statistic=str(item["statistic"]),
            is_counter=bool(item["is_counter"]),
        )
        for item in semantics
    ]
    power_indexes = [
        index
        for index, item in enumerate(semantics)
        if item["value_semantics"] == "anonymized-rated-power-scaled"
        and item["statistic"] == "average"
    ]
    base_groups: dict[str, dict[str, int]] = {}
    for index, item in enumerate(semantics):
        base_groups.setdefault(str(item["base_sensor"]), {})[str(item["statistic"])] = index

    digest = hashlib.sha256()
    row_count = 0
    status_counts: Counter[str] = Counter()
    split_counts: Counter[str] = Counter()
    minimum_row_id: int | None = None
    maximum_row_id: int | None = None
    previous_row_id: int | None = None
    duplicate_row_id_count = 0
    non_monotonic_row_id_count = 0
    seen_row_ids: set[int] = set()
    anonymous_time_min: datetime | None = None
    anonymous_time_max: datetime | None = None
    previous_anonymous_time: datetime | None = None
    nonpositive_time_step_count = 0
    sampling_interval_seconds: Counter[int] = Counter()
    with event_path.open("rb") as handle:
        raw_header = handle.readline()
        digest.update(raw_header)
        try:
            header = tuple(raw_header.decode("utf-8-sig").rstrip("\r\n").split(";"))
        except UnicodeDecodeError as exc:
            raise CareContractError(f"event {event_id} has an invalid UTF-8 header") from exc
        if header != expected_header:
            raise CareContractError(f"event {event_id} header does not match the quality contract")
        for line_number, raw_line in enumerate(handle, start=2):
            digest.update(raw_line)
            fields = raw_line.rstrip(b"\r\n").split(b";")
            if len(fields) != len(expected_header):
                raise CareContractError(
                    f"event {event_id} line {line_number} does not match the schema width"
                )
            try:
                source_time = fields[0].decode("utf-8")
                source_row_id = int(fields[2])
                split = fields[3].decode("utf-8")
                status_id = fields[4].decode("utf-8")
                anonymous_time = datetime.fromisoformat(source_time)
            except (UnicodeDecodeError, ValueError) as exc:
                raise CareContractError(
                    f"event {event_id} line {line_number} has invalid metadata"
                ) from exc
            if split not in {"train", "prediction"}:
                raise CareContractError(
                    f"event {event_id} line {line_number} has invalid split {split!r}"
                )
            parsed = [_parse_value(raw) for raw in fields[len(METADATA_COLUMNS) :]]
            finite_power = [
                parsed[index][0]
                for index in power_indexes
                if parsed[index][1] == "finite" and parsed[index][0] is not None
            ]
            if not finite_power:
                power_state = "unknown"
            elif any(value != 0.0 for value in finite_power):
                power_state = "nonzero"
            else:
                power_state = "zero"
            for accumulator, (value, category) in zip(accumulators, parsed, strict=True):
                accumulator.observe(
                    value=value,
                    category=category,
                    source_row_id=source_row_id,
                    status_id=status_id,
                    power_state=power_state,
                    farm=farm,
                    zero_run_min_length=zero_run_min_length,
                )
            for group in base_groups.values():
                required = {"minimum", "average", "maximum"}
                if not required.issubset(group):
                    continue
                minimum_value, minimum_category = parsed[group["minimum"]]
                average_value, average_category = parsed[group["average"]]
                maximum_value, maximum_category = parsed[group["maximum"]]
                if (
                    minimum_category == average_category == maximum_category == "finite"
                    and minimum_value is not None
                    and average_value is not None
                    and maximum_value is not None
                    and not minimum_value <= average_value <= maximum_value
                ):
                    for statistic in required:
                        accumulators[group[statistic]].min_avg_max_violation_count += 1

            if source_row_id in seen_row_ids:
                duplicate_row_id_count += 1
            seen_row_ids.add(source_row_id)
            if previous_row_id is not None and source_row_id <= previous_row_id:
                non_monotonic_row_id_count += 1
            previous_row_id = source_row_id
            minimum_row_id = (
                source_row_id if minimum_row_id is None else min(minimum_row_id, source_row_id)
            )
            maximum_row_id = (
                source_row_id if maximum_row_id is None else max(maximum_row_id, source_row_id)
            )
            if previous_anonymous_time is not None:
                interval = int((anonymous_time - previous_anonymous_time).total_seconds())
                sampling_interval_seconds[interval] += 1
                if interval <= 0:
                    nonpositive_time_step_count += 1
            previous_anonymous_time = anonymous_time
            anonymous_time_min = (
                anonymous_time
                if anonymous_time_min is None
                else min(anonymous_time_min, anonymous_time)
            )
            anonymous_time_max = (
                anonymous_time
                if anonymous_time_max is None
                else max(anonymous_time_max, anonymous_time)
            )
            status_counts[status_id] += 1
            split_counts[split] += 1
            row_count += 1

    if digest.hexdigest() != event["file_sha256"]:
        raise CareContractError(f"event {event_id} source file hash changed during quality audit")
    if row_count != int(event["row_count"]):
        raise CareContractError(f"event {event_id} row count changed during quality audit")
    for accumulator in accumulators:
        accumulator.finish(farm=farm, zero_run_min_length=zero_run_min_length)
    masks = [mask for accumulator in accumulators for mask in accumulator.mask_ranges]
    masks.sort(key=lambda item: (str(item["source_column"]), int(item["source_row_id_start"])))
    feature_summaries = [accumulator.summary() for accumulator in accumulators]
    payload: dict[str, Any] = {
        "quality_report_schema_version": "care-v6-event-quality-report-v1",
        "quality_rule_version": QUALITY_RULE_VERSION,
        "feature_set_version": quality_contract["feature_set_version"],
        "feature_set_sha256": quality_contract["feature_set_sha256"],
        "source_manifest_sha256": manifest["manifest_sha256"],
        "source_event_file_sha256": event["file_sha256"],
        "dataset_id": DATASET_ID,
        "dataset_version": DATASET_VERSION,
        "farm": farm,
        "event_id": event_id,
        "source_asset_id": event["source_asset_id"],
        "source_relative_path": event["relative_path"],
        "raw_values_modified": False,
        "timestamp_semantics": "independently-shifted-anonymized",
        "cross_event_ordering_allowed": False,
        "row_count": row_count,
        "source_row_id_min": minimum_row_id,
        "source_row_id_max": maximum_row_id,
        "duplicate_source_row_id_count": duplicate_row_id_count,
        "non_monotonic_source_row_id_count": non_monotonic_row_id_count,
        "source_time_stamp_min": anonymous_time_min.isoformat(sep=" ")
        if anonymous_time_min
        else None,
        "source_time_stamp_max": anonymous_time_max.isoformat(sep=" ")
        if anonymous_time_max
        else None,
        "sampling_interval_seconds": {
            str(interval): count for interval, count in sorted(sampling_interval_seconds.items())
        },
        "nonpositive_time_step_count": nonpositive_time_step_count,
        "split_counts": dict(sorted(split_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "zero_run_min_length": zero_run_min_length,
        "feature_summaries": feature_summaries,
        "quality_mask_ranges": masks,
    }
    return {**payload, "quality_report_sha256": _canonical_hash(payload)}


def _write_json(output_path: Path, value: Mapping[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output_path)


def _require_output_outside_source(dataset_root: Path | None, output_path: Path) -> None:
    if dataset_root is not None and output_path.resolve().is_relative_to(dataset_root.resolve()):
        raise CareContractError("quality output must not modify the read-only CARE source")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and run CARE v6 quality contracts")
    subparsers = parser.add_subparsers(dest="command", required=True)
    contract_parser = subparsers.add_parser("contract")
    contract_parser.add_argument("--manifest", type=Path, required=True)
    contract_parser.add_argument("--output", type=Path, required=True)
    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("--manifest", type=Path, required=True)
    audit_parser.add_argument("--quality-contract", type=Path, required=True)
    audit_parser.add_argument("--dataset-root", type=Path, required=True)
    audit_parser.add_argument("--event-id", type=int, required=True)
    audit_parser.add_argument("--output", type=Path, required=True)
    audit_parser.add_argument(
        "--zero-run-min-length", type=int, default=DEFAULT_ZERO_RUN_MIN_LENGTH
    )
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if args.command == "contract":
        _require_output_outside_source(None, args.output)
        contract = build_quality_contract(manifest)
        _write_json(args.output, contract)
        print(
            "CARE v6 quality contract generated: "
            f"{contract['summary']['feature_mapping_count']} mappings, "
            f"sha256={contract['quality_contract_sha256']}"
        )
        return 0

    _require_output_outside_source(args.dataset_root, args.output)
    quality_contract = json.loads(args.quality_contract.read_text(encoding="utf-8"))
    report = audit_event_quality(
        manifest,
        quality_contract,
        args.dataset_root,
        args.event_id,
        zero_run_min_length=args.zero_run_min_length,
    )
    _write_json(args.output, report)
    print(
        f"CARE v6 event {args.event_id} quality audit generated: "
        f"{report['row_count']} rows, {len(report['feature_summaries'])} features, "
        f"{len(report['quality_mask_ranges'])} mask ranges, "
        f"sha256={report['quality_report_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
