from __future__ import annotations

import hashlib
import re
from importlib import metadata
from pathlib import Path

import pytest

from windops_backend.benchmarks.care.dependency_closure import (
    BENCHMARK_DISTRIBUTIONS,
    CARE_CLI_ENTRYPOINTS,
    CareDependencyClosureError,
    verify_benchmark_dependency_closure,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_LOCK = BACKEND_ROOT / "requirements.container.txt"
UV_LOCK = BACKEND_ROOT / "uv.lock"


def test_locked_benchmark_dependency_closure_imports_and_runs_every_care_cli() -> None:
    report = verify_benchmark_dependency_closure(REQUIREMENTS_LOCK, uv_lock=UV_LOCK)

    assert report["status"] == "passed"
    assert (
        report["requirements_lock_sha256"]
        == hashlib.sha256(REQUIREMENTS_LOCK.read_bytes()).hexdigest()
    )
    assert report["uv_lock_sha256"] == hashlib.sha256(UV_LOCK.read_bytes()).hexdigest()
    assert report["packages"] == {
        distribution: metadata.version(distribution) for distribution in BENCHMARK_DISTRIBUTIONS
    }
    assert report["cli_entrypoints"] == list(CARE_CLI_ENTRYPOINTS)


def test_dependency_closure_rejects_missing_or_version_drifted_lock(
    tmp_path: Path,
) -> None:
    contents = REQUIREMENTS_LOCK.read_text(encoding="utf-8")
    missing = tmp_path / "missing.txt"
    missing.write_text(
        re.sub(r"(?ms)^pyarrow==.*?(?=^[a-z0-9]|\Z)", "", contents),
        encoding="utf-8",
    )
    with pytest.raises(CareDependencyClosureError, match="missing benchmark package pyarrow"):
        verify_benchmark_dependency_closure(missing)

    drifted = tmp_path / "drifted.txt"
    drifted.write_text(
        re.sub(r"(?m)^pyarrow==[^\s\\]+", "pyarrow==0.0.0", contents),
        encoding="utf-8",
    )
    with pytest.raises(CareDependencyClosureError, match="expected locked 0.0.0"):
        verify_benchmark_dependency_closure(drifted)


def test_dependency_closure_rejects_missing_care_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from windops_backend.benchmarks.care import dependency_closure

    real_which = dependency_closure.shutil.which
    monkeypatch.setattr(
        dependency_closure.shutil,
        "which",
        lambda name: None if name == "windops-care-full-scale" else real_which(name),
    )
    with pytest.raises(CareDependencyClosureError, match="windops-care-full-scale"):
        verify_benchmark_dependency_closure(REQUIREMENTS_LOCK)
