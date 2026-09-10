from __future__ import annotations

from typing import Any

from scripts.check_coverage_budget import (
    CRITICAL_MODULE_MINIMUMS,
    DIFF_LINE_MINIMUM,
    evaluate_coverage,
    parse_changed_lines,
)


def _report(*, total: float, module: float, executed: list[int]) -> dict[str, Any]:
    missing = [line for line in (10, 11, 12, 20) if line not in executed]
    return {
        "totals": {"percent_covered": total},
        "files": {
            "src/windops_backend/services/workflow.py": {
                "summary": {"percent_covered": module},
                "executed_lines": executed,
                "missing_lines": missing,
            }
        },
    }


def test_parse_changed_lines_normalises_backend_paths_and_skips_deletions() -> None:
    diff = """diff --git a/workflow.py b/workflow.py
--- a/backend/src/windops_backend/services/workflow.py
+++ b/backend/src/windops_backend/services/workflow.py
@@ -8,0 +10,3 @@
+one
+two
+three
diff --git a/backend/src/deleted.py b/backend/src/deleted.py
--- a/backend/src/deleted.py
+++ /dev/null
@@ -1 +0,0 @@
-gone
"""

    assert parse_changed_lines(diff) == {"src/windops_backend/services/workflow.py": {10, 11, 12}}
    assert DIFF_LINE_MINIMUM == 65.5


def test_coverage_budget_accepts_global_module_and_diff_thresholds() -> None:
    report = _report(total=75.0, module=90.0, executed=[10, 11, 12, 20])
    diff = """+++ b/backend/src/windops_backend/services/workflow.py
@@ -9,0 +10,3 @@
"""

    result = evaluate_coverage(
        report,
        diff_text=diff,
        global_minimum=70.0,
        diff_minimum=80.0,
        critical_minimums={"src/windops_backend/services/workflow.py": 80.0},
    )

    assert result.passed
    assert result.diff_executable_lines == 3
    assert result.diff_covered_lines == 3


def test_coverage_budget_reports_each_regression_without_short_circuiting() -> None:
    report = _report(total=67.0, module=70.0, executed=[10, 20])
    diff = """+++ b/backend/src/windops_backend/services/workflow.py
@@ -9,0 +10,3 @@
"""

    result = evaluate_coverage(
        report,
        diff_text=diff,
        global_minimum=68.0,
        diff_minimum=80.0,
        critical_minimums={
            "src/windops_backend/services/workflow.py": 80.0,
            "src/windops_backend/services/missing.py": 80.0,
        },
    )

    assert not result.passed
    assert result.diff_executable_lines == 3
    assert result.diff_covered_lines == 1
    assert any("global line coverage" in failure for failure in result.failures)
    assert any("workflow.py line coverage" in failure for failure in result.failures)
    assert any("absent from coverage report" in failure for failure in result.failures)
    assert any("changed executable line coverage" in failure for failure in result.failures)


def test_coverage_budget_allows_a_diff_without_executable_python_lines() -> None:
    result = evaluate_coverage(
        _report(total=75.0, module=90.0, executed=[10]),
        diff_text="+++ b/docs/release.md\n@@ -0,0 +1,2 @@\n",
        global_minimum=70.0,
        critical_minimums={"src/windops_backend/services/workflow.py": 80.0},
    )

    assert result.passed
    assert result.diff_executable_lines == 0


def test_high_risk_service_floors_cannot_regress_to_the_audited_weak_baseline() -> None:
    assert CRITICAL_MODULE_MINIMUMS["src/windops_backend/services/workorders.py"] >= 88.0
    assert CRITICAL_MODULE_MINIMUMS["src/windops_backend/services/workflow.py"] >= 58.0
    assert CRITICAL_MODULE_MINIMUMS["src/windops_backend/services/platform_governance.py"] >= 58.0
    assert CRITICAL_MODULE_MINIMUMS["src/windops_backend/services/operational_views.py"] >= 55.0
    assert CRITICAL_MODULE_MINIMUMS["src/windops_backend/services/alarms.py"] >= 80.0
    assert CRITICAL_MODULE_MINIMUMS["src/windops_backend/services/agent_governance.py"] >= 52.0
