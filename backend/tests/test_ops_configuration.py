from pathlib import Path

import yaml

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent


def test_slo_and_alert_configuration_is_complete() -> None:
    slo = yaml.safe_load((BACKEND_ROOT / "ops" / "slo.yaml").read_text(encoding="utf-8"))
    objectives = {objective["id"] for objective in slo["spec"]["objectives"]}
    assert objectives == {
        "http-availability",
        "http-p95-latency",
        "agent-success",
        "telemetry-freshness",
    }

    rules = yaml.safe_load(
        (BACKEND_ROOT / "ops" / "prometheus-alerts.yaml").read_text(encoding="utf-8")
    )
    alerts = {
        rule["alert"]: rule
        for group in rules["groups"]
        for rule in group["rules"]
        if "alert" in rule
    }
    assert set(alerts) == {
        "WindOpsHttpErrorBudgetFastBurn",
        "WindOpsHttpErrorBudgetSlowBurn",
        "WindOpsHttpP95LatencyHigh",
        "WindOpsAgentSuccessLow",
        "WindOpsTelemetryStale",
        "WindOpsMetricsAbsent",
    }
    assert alerts["WindOpsHttpErrorBudgetFastBurn"]["labels"]["severity"] == "page"
    assert "14.4" in alerts["WindOpsHttpErrorBudgetFastBurn"]["expr"]
    runbook = (PROJECT_ROOT / "docs" / "runbooks" / "incident-response.md").read_text(
        encoding="utf-8"
    )
    for heading in (
        "## HTTP error budget",
        "## Latency",
        "## Agent failure",
        "## Telemetry stale",
        "## Metrics absent",
    ):
        assert heading in runbook


def test_otel_collector_uses_bounded_batching_and_external_export() -> None:
    collector_path = BACKEND_ROOT / "ops" / "otel-collector.yaml"
    raw = collector_path.read_text(encoding="utf-8")
    collector = yaml.safe_load(raw)
    trace_pipeline = collector["service"]["pipelines"]["traces"]
    assert trace_pipeline["processors"] == ["memory_limiter", "batch"]
    assert trace_pipeline["exporters"] == ["otlphttp/managed"]
    assert collector["exporters"]["otlphttp/managed"]["sending_queue"]["enabled"] is True
    assert collector["exporters"]["otlphttp/managed"]["retry_on_failure"]["enabled"] is True
    assert "${env:WINDOPS_OBSERVABILITY_EXPORT_ENDPOINT}" in raw
    assert "logging" not in collector["exporters"]


def test_release_runbook_keeps_external_gates_fail_closed() -> None:
    runbook = (PROJECT_ROOT / "docs" / "runbooks" / "release-acceptance.md").read_text(
        encoding="utf-8"
    )
    for required in (
        "0015_alarm_command_state",
        'WINDOPS_RUN_EXTERNAL_RELEASE_TESTS = "1"',
        "tests/external/test_release_environment.py",
        "windops-dr-drill",
        "DAST",
        "WCAG",
        "Sites",
        "测试跳过即视为失败",
    ):
        assert required in runbook


def test_postgres_migration_recovery_runbook_is_fail_closed() -> None:
    runbook = (PROJECT_ROOT / "docs" / "runbooks" / "postgresql-migration-recovery.md").read_text(
        encoding="utf-8"
    )
    for required in (
        "0015_alarm_command_state",
        "alembic current",
        "Do not run `alembic stamp`",
        "Restore",
        "WINDOPS_FAIL_ON_SKIPPED=1",
        "Outbox atomic claim",
        "skipped PostgreSQL contract test is a failed gate",
    ):
        assert required in runbook


def test_ci_has_a_non_skipping_pinned_postgres_contract_gate() -> None:
    workflow = yaml.safe_load(
        (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["postgres-contract"]
    image = job["services"]["postgres"]["image"]
    assert image.startswith("timescale/timescaledb-ha@sha256:")
    assert len(image.removeprefix("timescale/timescaledb-ha@sha256:")) == 64
    assert job["env"]["WINDOPS_RUN_POSTGRES_CONTRACT_TESTS"] == "1"
    assert job["env"]["WINDOPS_RUN_POSTGRES_CONCURRENCY_TESTS"] == "1"
    assert job["env"]["WINDOPS_FAIL_ON_SKIPPED"] == "1"
    commands = "\n".join(
        str(step.get("run", "")) for step in job["steps"] if isinstance(step, dict)
    )
    for required in (
        "alembic upgrade head",
        "test_postgres_migrations.py",
        "test_postgres_concurrency.py",
        "test_postgres_service_resilience.py",
        "test_postgres_prediction_lock.py",
        "--junitxml",
    ):
        assert required in commands
