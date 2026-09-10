"""Fail a release when any required CI check is missing or not successful."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from typing import Any

REQUIRED_CHECKS = frozenset(
    {
        "frontend",
        "backend",
        "postgres-contract",
        "care-postgres-contract",
        "browser-e2e",
        "real-cross-layer-e2e",
    }
)


def _check_runs(lines: Iterable[str]) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            runs.append(value)
    return runs


def verify_release_checks(check_runs: Iterable[dict[str, Any]], commit_sha: str) -> list[str]:
    by_name: dict[str, list[dict[str, Any]]] = {}
    for check in check_runs:
        name = check.get("name")
        if isinstance(name, str):
            by_name.setdefault(name, []).append(check)
    failures: list[str] = []
    for required in sorted(REQUIRED_CHECKS):
        matches = [
            check for check in by_name.get(required, []) if check.get("head_sha") == commit_sha
        ]
        if not matches:
            failures.append(f"{required}: missing for target commit")
            continue
        if not any(
            check.get("status") == "completed" and check.get("conclusion") == "success"
            for check in matches
        ):
            conclusions = ", ".join(
                f"{check.get('status')}/{check.get('conclusion')}" for check in matches
            )
            failures.append(f"{required}: no completed successful run ({conclusions})")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()
    failures = verify_release_checks(_check_runs(sys.stdin), args.sha)
    if failures:
        for failure in failures:
            print(f"release check gate failed: {failure}", file=sys.stderr)
        return 1
    print("release check gate passed: " + ", ".join(sorted(REQUIRED_CHECKS)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
