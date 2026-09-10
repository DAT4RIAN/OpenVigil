from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GLOBAL_LINE_MINIMUM = 68.0
DIFF_LINE_MINIMUM = 65.5
CRITICAL_MODULE_MINIMUMS = {
    "src/windops_backend/access_control.py": 80.0,
    "src/windops_backend/api/assets.py": 38.5,
    "src/windops_backend/api/model_registry.py": 48.0,
    "src/windops_backend/api/scada.py": 48.5,
    "src/windops_backend/identity.py": 90.0,
    "src/windops_backend/knowledge_graph/store.py": 49.0,
    "src/windops_backend/platform_configuration.py": 80.0,
    "src/windops_backend/security.py": 90.0,
    "src/windops_backend/services/agent_governance.py": 52.0,
    "src/windops_backend/services/alarms.py": 80.0,
    "src/windops_backend/services/dashboard.py": 39.0,
    "src/windops_backend/services/idempotency.py": 80.0,
    "src/windops_backend/services/missions.py": 45.0,
    "src/windops_backend/services/operational_views.py": 55.0,
    "src/windops_backend/services/platform_governance.py": 58.0,
    "src/windops_backend/services/workflow.py": 58.0,
    "src/windops_backend/services/workorders.py": 88.0,
    "src/windops_backend/storage.py": 80.0,
}
_HUNK_PATTERN = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True)
class CoverageResult:
    failures: tuple[str, ...]
    diff_executable_lines: int
    diff_covered_lines: int

    @property
    def passed(self) -> bool:
        return not self.failures


def _normalise_source_path(raw_path: str) -> str:
    path = raw_path.replace("\\", "/")
    marker = "src/windops_backend/"
    marker_index = path.find(marker)
    if marker_index >= 0:
        return path[marker_index:]
    return path.removeprefix("backend/").removeprefix("./")


def _summary_percent(summary: dict[str, Any]) -> float:
    return float(summary["percent_covered"])


def parse_changed_lines(diff_text: str) -> dict[str, set[int]]:
    changed: dict[str, set[int]] = {}
    current_path: str | None = None
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            raw_path = line[4:].split("\t", 1)[0]
            current_path = None if raw_path == "/dev/null" else _normalise_source_path(raw_path)
            continue
        match = _HUNK_PATTERN.match(line)
        if current_path is None or match is None:
            continue
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        if count:
            changed.setdefault(current_path, set()).update(range(start, start + count))
    return changed


def evaluate_coverage(
    report: dict[str, Any],
    *,
    diff_text: str | None = None,
    global_minimum: float = GLOBAL_LINE_MINIMUM,
    diff_minimum: float = DIFF_LINE_MINIMUM,
    critical_minimums: dict[str, float] | None = None,
) -> CoverageResult:
    failures: list[str] = []
    global_percent = _summary_percent(report["totals"])
    if global_percent < global_minimum:
        failures.append(
            f"global line coverage {global_percent:.2f}% is below {global_minimum:.2f}%"
        )

    normalised_files = {
        _normalise_source_path(path): details for path, details in report["files"].items()
    }
    for module, minimum in (critical_minimums or CRITICAL_MODULE_MINIMUMS).items():
        details = normalised_files.get(_normalise_source_path(module))
        if details is None:
            failures.append(f"critical module is absent from coverage report: {module}")
            continue
        percent = _summary_percent(details["summary"])
        if percent < minimum:
            failures.append(
                f"critical module {module} line coverage {percent:.2f}% is below {minimum:.2f}%"
            )

    executable_diff_lines = 0
    covered_diff_lines = 0
    if diff_text is not None:
        for path, changed_lines in parse_changed_lines(diff_text).items():
            details = normalised_files.get(path)
            if details is None:
                continue
            executed = set(details.get("executed_lines", []))
            missing = set(details.get("missing_lines", []))
            executable = changed_lines & (executed | missing)
            executable_diff_lines += len(executable)
            covered_diff_lines += len(executable & executed)
        if executable_diff_lines:
            diff_percent = covered_diff_lines / executable_diff_lines * 100
            if diff_percent < diff_minimum:
                failures.append(
                    f"changed executable line coverage {diff_percent:.2f}% "
                    f"({covered_diff_lines}/{executable_diff_lines}) is below {diff_minimum:.2f}%"
                )

    return CoverageResult(
        failures=tuple(failures),
        diff_executable_lines=executable_diff_lines,
        diff_covered_lines=covered_diff_lines,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enforce global, critical-module, and changed-line coverage budgets"
    )
    parser.add_argument("--coverage-json", type=Path, required=True)
    parser.add_argument("--diff-file", type=Path)
    args = parser.parse_args()

    report = json.loads(args.coverage_json.read_text(encoding="utf-8"))
    diff_text = args.diff_file.read_text(encoding="utf-8") if args.diff_file else None
    result = evaluate_coverage(report, diff_text=diff_text)
    if not result.passed:
        for failure in result.failures:
            print(f"COVERAGE BUDGET FAILED: {failure}")
        return 1

    totals = report["totals"]
    message = f"Coverage budget passed: global line coverage {_summary_percent(totals):.2f}%"
    if result.diff_executable_lines:
        diff_percent = result.diff_covered_lines / result.diff_executable_lines * 100
        message += f", changed executable lines {diff_percent:.2f}%"
    else:
        message += ", no changed executable lines"
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
