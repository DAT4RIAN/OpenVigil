from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from windops_backend.benchmarks.care.quality import QUALITY_RULE_VERSION
from windops_backend.benchmarks.care.replay import (
    CARE_REPLAY_SOURCE_ID,
    MAX_INGEST_BATCH_SIZE,
    MAX_ONLINE_TURBINE_ID_LENGTH,
    MAX_SOURCE_EVENT_ID_LENGTH,
    REPLAY_CONTRACT_VERSION,
    SYNTHETIC_TIME_CLAIM,
    BenchmarkReplayRun,
    CareReplayError,
    ReplayCheckpoint,
    ReplaySourceRow,
    ReplayVariable,
    advance_checkpoint,
    build_replay_contract,
    build_replay_sample,
    build_source_event_id,
    choose_query_plan,
    create_replay_run,
    iter_replay_batches,
    parse_source_event_id,
    replay_ingest_request,
    transition_replay_run,
    validate_replay_run_registry,
    validate_replay_window,
    verify_replay_contract,
    write_replay_contract,
)
from windops_backend.config import TelemetrySourcePolicy, TelemetryVariablePolicy
from windops_backend.models import Alarm, IngestStreamState, Mission, ScadaSample, Turbine


def _variable(name: str = "generator_bearing_temperature_avg", unit: str = "°C") -> ReplayVariable:
    return ReplayVariable(name, unit)


def _run(
    run_id: str = "run00001",
    *,
    event_id: int = 7,
    anchor: datetime | None = None,
    start: int = 10,
    end: int = 12,
    variables: tuple[ReplayVariable, ...] | None = None,
) -> BenchmarkReplayRun:
    now = datetime(2026, 8, 26, 10, 0, tzinfo=UTC)
    return create_replay_run(
        benchmark_replay_run_id=run_id,
        farm="A",
        event_id=event_id,
        source_asset_id="13",
        replay_anchor_at=anchor or now,
        selected_variables=variables or (_variable(),),
        window_start_row_id=start,
        window_end_row_id=end,
        created_by="care-test",
        created_at=now,
        model_id="care-model",
        deployment_id="care-deployment",
        threshold_policy_id="care-threshold",
    )


def _row(
    row_id: int,
    variables: tuple[ReplayVariable, ...],
    *,
    status: str = "0",
) -> ReplaySourceRow:
    return ReplaySourceRow(
        source_row_id=row_id,
        source_time_stamp=f"source-{row_id}",
        anonymous_observed_at=f"2022-01-01T00:{row_id:02d}:00",
        status_type_id=status,
        values=tuple(
            sorted((variable.canonical_variable, float(row_id)) for variable in variables)
        ),
        source_interval_seconds=600.0,
    )


def _sample(
    run: BenchmarkReplayRun,
    row_id: int,
    variable: ReplayVariable | None = None,
    *,
    status: str = "0",
    quality: str = "good",
) -> dict[str, Any]:
    selected = variable or run.selected_variables[0]
    return build_replay_sample(
        run,
        _row(row_id, run.selected_variables, status=status),
        selected,
        platform_quality=quality,  # type: ignore[arg-type]
        quality_rule_id=QUALITY_RULE_VERSION,
        quality_mask_refs=(f"mask-{row_id}",),
    )


def test_replay_contract_is_stable_and_semantically_fail_closed(tmp_path: Path) -> None:
    contract = build_replay_contract()
    assert contract["schema_version"] == REPLAY_CONTRACT_VERSION
    verify_replay_contract(contract)

    first = tmp_path / "replay-contract.json"
    second = tmp_path / "replay-contract-repeat.json"
    write_replay_contract(first, contract)
    write_replay_contract(second)
    assert first.read_bytes() == second.read_bytes()

    tampered = json.loads(json.dumps(contract))
    tampered["time_rule"]["interval_seconds"] = 300
    unsigned = {key: value for key, value in tampered.items() if key != "contract_sha256"}
    tampered["contract_sha256"] = hashlib.sha256(
        json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    with pytest.raises(CareReplayError, match="semantics differ"):
        verify_replay_contract(tampered)


def test_logical_asset_is_separate_from_event_and_run_online_instances() -> None:
    first = _run("run00001", event_id=7)
    overlapping_event = _run("run00002", event_id=8)
    repeated_event_new_run = _run("run00003", event_id=7)

    assert {
        item.logical_asset_id for item in (first, overlapping_event, repeated_event_new_run)
    } == {"CARE-A-13"}
    assert (
        len({item.online_turbine_id for item in (first, overlapping_event, repeated_event_new_run)})
        == 3
    )
    assert all(
        len(item.online_turbine_id) <= MAX_ONLINE_TURBINE_ID_LENGTH
        for item in (first, overlapping_event, repeated_event_new_run)
    )
    assert validate_replay_run_registry((first, overlapping_event, repeated_event_new_run))
    same_run_id_other_event = _run("run00001", event_id=8)
    with pytest.raises(CareReplayError, match="cannot be registered more than once"):
        validate_replay_run_registry((first, same_run_id_other_event))
    with pytest.raises(CareReplayError, match="exactly eight"):
        _run("same-prefix-but-truncated")


def test_replay_window_cannot_exceed_the_platform_custom_query_boundary() -> None:
    maximum_row_span = int(timedelta(days=365).total_seconds() // 600) - 1
    _run(start=0, end=maximum_row_span)
    with pytest.raises(CareReplayError, match="365-day query boundary"):
        _run(start=0, end=maximum_row_span + 1)


def test_source_event_identity_is_bounded_run_isolated_and_reversible() -> None:
    first = _run("run00001")
    second = _run("run00002")
    variable = first.selected_variables[0]
    first_id = build_source_event_id(first, 10, variable)
    second_id = build_source_event_id(second, 10, second.selected_variables[0])

    assert first_id != second_id
    assert len(first_id) <= MAX_SOURCE_EVENT_ID_LENGTH
    identity = parse_source_event_id(first, first_id)
    assert identity.benchmark_replay_run_id == "run00001"
    assert identity.event_id == 7
    assert identity.source_row_id == 10
    assert first.variable_by_short_id(identity.variable_short_id) == variable
    with pytest.raises(CareReplayError, match="another replay run"):
        parse_source_event_id(second, first_id)


def test_synthetic_time_and_status_quality_semantics_are_deterministic() -> None:
    anchor = datetime(2026, 8, 26, 8, 0, tzinfo=UTC)
    run = _run(anchor=anchor)
    good = _sample(run, 12, status="99", quality="good")
    bad = _sample(run, 12, status="0", quality="bad")

    assert good == _sample(run, 12, status="99", quality="good")
    assert good["observed_at"] == (anchor + timedelta(minutes=20)).isoformat()
    assert good["source_sequence"] == 12
    assert good["attributes"]["source_time_stamp"] == "source-12"
    assert good["attributes"]["anonymous_observed_at"].startswith("2022-")
    assert good["attributes"]["observed_at_is_synthetic"] is True
    assert good["attributes"]["time_claim"] == SYNTHETIC_TIME_CLAIM
    assert good["attributes"]["status_is_platform_quality"] is False
    assert good["quality"] == "good" and bad["quality"] == "bad"
    assert good["attributes"]["status_type_id"] == "99"
    assert bad["attributes"]["status_type_id"] == "0"


@pytest.mark.parametrize(
    ("start_delta", "expected"),
    [
        (timedelta(minutes=5), "LIVE"),
        (timedelta(hours=3), "24H"),
        (timedelta(days=2), "30D"),
        (timedelta(days=60), "CUSTOM"),
    ],
)
def test_query_plan_finds_synthetic_data_without_real_time_claim(
    start_delta: timedelta,
    expected: str,
) -> None:
    reference = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
    run = _run(anchor=reference - start_delta, start=10, end=10)
    plan = choose_query_plan(run, reference_at=reference)
    assert plan.range_name == expected
    assert plan.contains(run.replay_anchor_at)
    assert plan.observed_at_is_synthetic is True
    assert plan.time_claim == SYNTHETIC_TIME_CLAIM

    future = _run(anchor=reference + timedelta(seconds=1), start=10, end=10)
    with pytest.raises(CareReplayError, match="future"):
        choose_query_plan(future, reference_at=reference)


def test_batches_checkpoint_restart_and_retry_are_deterministic() -> None:
    variables = (_variable(), _variable("generator_speed_avg", "rpm"))
    run = _run(variables=variables)
    rows = [_row(row_id, run.selected_variables) for row_id in range(10, 13)]
    batches = list(
        iter_replay_batches(run, rows, quality_rule_id=QUALITY_RULE_VERSION, batch_size=2)
    )
    assert [len(batch) for batch in batches] == [2, 2, 2]
    assert [sample["source_sequence"] for batch in batches for sample in batch] == [
        10,
        10,
        11,
        11,
        12,
        12,
    ]
    assert replay_ingest_request(batches[0])["source_id"] == CARE_REPLAY_SOURCE_ID

    advanced = advance_checkpoint(run, batches[0])
    assert advanced.checkpoint.revision == 1
    assert {row for _variable_id, row in advanced.checkpoint.last_confirmed_rows} == {10}
    assert advance_checkpoint(advanced, batches[0]) == advanced

    restored_checkpoint = ReplayCheckpoint.from_document(advanced.checkpoint.to_document())
    restarted = replace(advanced, checkpoint=restored_checkpoint)
    remaining = list(
        iter_replay_batches(
            restarted,
            rows,
            quality_rule_id=QUALITY_RULE_VERSION,
            batch_size=MAX_INGEST_BATCH_SIZE,
        )
    )
    assert len(remaining) == 1
    assert [sample["source_sequence"] for sample in remaining[0]] == [11, 11, 12, 12]


def test_checkpoint_cannot_skip_rows_or_accept_another_run() -> None:
    run = _run()
    with pytest.raises(CareReplayError, match="unconfirmed row"):
        advance_checkpoint(run, [_sample(run, 12)])
    with pytest.raises(CareReplayError, match="another replay run"):
        advance_checkpoint(run, [_sample(_run("run00002"), 10)])


def test_replay_and_model_windows_fail_closed_across_event_or_run() -> None:
    first = _run("run00001", event_id=7)
    second = _run("run00002", event_id=7)
    third = _run("run00003", event_id=8)
    identity = validate_replay_window([_sample(first, 10), _sample(first, 11)])
    assert identity.benchmark_replay_run_id == first.benchmark_replay_run_id

    for mixed in (
        [_sample(first, 10), _sample(second, 10)],
        [_sample(first, 10), _sample(third, 10)],
    ):
        with pytest.raises(CareReplayError, match="cannot cross"):
            validate_replay_window(mixed)

    tampered = _sample(first, 10)
    tampered["source_sequence"] = 11
    with pytest.raises(CareReplayError, match="identity fields disagree"):
        validate_replay_window([tampered])


def test_batch_planning_rejects_gaps_and_oversized_requests() -> None:
    run = _run()
    with pytest.raises(CareReplayError, match="contiguous source IDs"):
        list(
            iter_replay_batches(
                run,
                [_row(10, run.selected_variables), _row(12, run.selected_variables)],
                quality_rule_id=QUALITY_RULE_VERSION,
            )
        )
    with pytest.raises(CareReplayError, match="between 1 and 1000"):
        replay_ingest_request([_sample(run, 10)] * (MAX_INGEST_BATCH_SIZE + 1))


def test_replay_lifecycle_requires_checkpoint_and_records_terminal_context() -> None:
    now = datetime(2026, 8, 26, 10, 0, tzinfo=UTC)
    run = transition_replay_run(_run(start=10, end=10), "running", at=now)
    with pytest.raises(CareReplayError, match="complete per-variable checkpoint"):
        transition_replay_run(run, "completed", at=now + timedelta(minutes=1))
    run = advance_checkpoint(run, [_sample(run, 10)])
    completed = transition_replay_run(run, "completed", at=now + timedelta(minutes=1))
    assert completed.status == "completed" and completed.finished_at is not None
    with pytest.raises(CareReplayError, match="invalid replay status transition"):
        transition_replay_run(completed, "running", at=now + timedelta(minutes=2))

    cancelling = transition_replay_run(
        transition_replay_run(_run("run00002"), "running", at=now),
        "cancelling",
        at=now,
        actor="operator-1",
    )
    cancelled = transition_replay_run(cancelling, "cancelled", at=now, actor="operator-1")
    assert cancelled.cancelled_by == "operator-1"


@pytest.mark.asyncio
async def test_platform_ingest_watermark_query_retry_restart_and_new_run_isolation(
    app: FastAPI,
    client: httpx.AsyncClient,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    variables = (_variable(), _variable("generator_speed_avg", "rpm"))
    run_one = _run(
        "live0001",
        anchor=now - timedelta(minutes=25),
        start=100,
        end=102,
        variables=variables,
    )
    run_two = _run(
        "live0002",
        anchor=now - timedelta(minutes=25),
        start=100,
        end=102,
        variables=variables,
    )
    app.state.settings.telemetry_source_policies[CARE_REPLAY_SOURCE_ID] = TelemetrySourcePolicy(
        display_name="Governed CARE v6 replay source",
        source_kind="rest",
        sequence_required=True,
        max_lateness_seconds=900,
        max_future_skew_seconds=120,
        allowed_turbines=[run_one.online_turbine_id, run_two.online_turbine_id],
        allowed_variables=[item.canonical_variable for item in variables],
        variable_contracts={
            item.canonical_variable: TelemetryVariablePolicy(
                label=item.canonical_variable,
                unit=item.unit,
                precision=2,
                normal_min=0,
                normal_max=1000,
            )
            for item in variables
        },
    )
    async with app.state.session_factory() as session, session.begin():
        session.add_all(
            [
                Turbine(
                    id=run.online_turbine_id,
                    wind_farm_id="WF-EAST-01",
                    model="CARE v6 isolated replay",
                    status="running",
                    health_score=100,
                )
                for run in (run_one, run_two)
            ]
        )
        alarm_count_before = int(await session.scalar(select(func.count(Alarm.id))) or 0)
        mission_count_before = int(await session.scalar(select(func.count(Mission.id))) or 0)

    variable_one, variable_two = run_one.selected_variables

    async def ingest(sample: dict[str, Any]) -> httpx.Response:
        return await client.post(
            "/api/v1/scada/ingest",
            json={"source_id": CARE_REPLAY_SOURCE_ID, "samples": [sample]},
        )

    row_101 = _sample(run_one, 101, variable_one)
    accepted = await ingest(row_101)
    assert accepted.status_code == 202 and accepted.json()["accepted"] == 1

    out_of_order = await ingest(_sample(run_one, 100, variable_one))
    assert out_of_order.json()["accepted"] == 1
    assert out_of_order.json()["results"][0]["late"] is True

    repeated = await ingest(row_101)
    assert repeated.json()["duplicates"] == 1

    assert (await ingest(_sample(run_one, 102, variable_one))).json()["accepted"] == 1
    assert (await ingest(_sample(run_one, 102, variable_two))).json()["accepted"] == 1
    too_late = await ingest(_sample(run_one, 100, variable_two))
    assert too_late.json()["quarantined"] == 1
    assert too_late.json()["results"][0]["reason_code"] == "beyond_lateness_window"

    new_run = await ingest(
        _sample(run_two, 100, run_two.variable_by_name(variable_one.canonical_variable))
    )
    assert new_run.json()["accepted"] == 1

    history = await client.get(
        "/api/v1/scada/history",
        params={
            "turbine_id": run_one.online_turbine_id,
            "range": "24H",
            "points_per_series": 2000,
        },
    )
    assert history.status_code == 200
    assert history.json()["meta"]["range"] == "24H"
    assert history.json()["meta"]["point_count"] == 4
    assert {series["source_id"] for series in history.json()["data"]} == {CARE_REPLAY_SOURCE_ID}

    async with app.state.session_factory() as session:
        run_one_samples = list(
            (
                await session.scalars(
                    select(ScadaSample).where(ScadaSample.turbine_id == run_one.online_turbine_id)
                )
            ).all()
        )
        run_two_samples = list(
            (
                await session.scalars(
                    select(ScadaSample).where(ScadaSample.turbine_id == run_two.online_turbine_id)
                )
            ).all()
        )
        assert len(run_one_samples) == 4 and len(run_two_samples) == 1
        assert all(
            sample.attributes["time_claim"] == SYNTHETIC_TIME_CLAIM
            and sample.attributes["observed_at_is_synthetic"] is True
            for sample in [*run_one_samples, *run_two_samples]
        )
        streams = list(
            (
                await session.scalars(
                    select(IngestStreamState).where(
                        IngestStreamState.source_id == CARE_REPLAY_SOURCE_ID
                    )
                )
            ).all()
        )
        assert len(streams) == 3
        stream_by_key = {stream.stream_key: stream for stream in streams}
        primary = stream_by_key[f"{run_one.online_turbine_id}:{variable_one.canonical_variable}"]
        assert primary.highest_sequence == 102
        assert primary.accepted_count == 3
        assert primary.late_count == 1
        assert primary.duplicate_count == 1
        secondary = stream_by_key[f"{run_one.online_turbine_id}:{variable_two.canonical_variable}"]
        assert secondary.highest_sequence == 102
        assert secondary.quarantined_count == 1
        assert int(await session.scalar(select(func.count(Alarm.id))) or 0) == alarm_count_before
        assert (
            int(await session.scalar(select(func.count(Mission.id))) or 0) == mission_count_before
        )
