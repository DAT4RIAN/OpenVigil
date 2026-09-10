from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess  # nosec B404
import tempfile
from importlib import metadata
from pathlib import Path
from typing import Any


class CareDependencyClosureError(RuntimeError):
    """Raised when a CARE execution environment is not lock-complete."""


BENCHMARK_DISTRIBUTIONS = {
    "joblib": "joblib",
    "numpy": "numpy",
    "pyarrow": "pyarrow",
    "scikit-learn": "sklearn",
    "scipy": "scipy",
    "threadpoolctl": "threadpoolctl",
}
CARE_IMPORTS = (
    "windops_backend.benchmarks.care.contract",
    "windops_backend.benchmarks.care.quality",
    "windops_backend.benchmarks.care.scoring",
    "windops_backend.benchmarks.care.replay",
    "windops_backend.benchmarks.care.anomaly",
    "windops_backend.benchmarks.care.pipeline",
    "windops_backend.benchmarks.care.importer",
    "windops_backend.benchmarks.care.evaluation",
    "windops_backend.benchmarks.care.fullscale",
)
CARE_CLI_ENTRYPOINTS = (
    "windops-care-contract",
    "windops-care-quality",
    "windops-care-score",
    "windops-care-replay-contract",
    "windops-care-anomaly-contract",
    "windops-care-pipeline",
    "windops-care-minimal-import",
    "windops-care-offline-evaluate",
    "windops-care-full-scale",
    "windops-care-workload-smoke",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise_distribution(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _locked_versions(path: Path) -> dict[str, str]:
    try:
        contents = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise CareDependencyClosureError("container requirements lock is unreadable") from exc
    if "--hash=sha256:" not in contents:
        raise CareDependencyClosureError("container requirements must be hash locked")
    return {
        _normalise_distribution(name): version
        for name, version in re.findall(r"(?m)^([A-Za-z0-9][A-Za-z0-9_.-]*)==([^\s\\]+)", contents)
    }


def verify_benchmark_dependency_closure(
    requirements_lock: Path,
    *,
    uv_lock: Path | None = None,
) -> dict[str, Any]:
    requirements_lock = requirements_lock.resolve(strict=True)
    locked = _locked_versions(requirements_lock)
    package_versions: dict[str, str] = {}
    for distribution, module in BENCHMARK_DISTRIBUTIONS.items():
        expected = locked.get(distribution)
        if expected is None:
            raise CareDependencyClosureError(
                f"container requirements are missing benchmark package {distribution}"
            )
        try:
            installed = metadata.version(distribution)
            importlib.import_module(module)
        except (ImportError, metadata.PackageNotFoundError) as exc:
            raise CareDependencyClosureError(
                f"benchmark package {distribution} is not installed and importable"
            ) from exc
        if installed != expected:
            raise CareDependencyClosureError(
                f"benchmark package {distribution} is {installed}, expected locked {expected}"
            )
        package_versions[distribution] = installed

    for module in CARE_IMPORTS:
        try:
            importlib.import_module(module)
        except ImportError as exc:
            raise CareDependencyClosureError(f"CARE module import failed: {module}") from exc

    cli_paths: dict[str, str] = {}
    for entrypoint in CARE_CLI_ENTRYPOINTS:
        executable = shutil.which(entrypoint)
        if executable is None:
            raise CareDependencyClosureError(f"CARE CLI entrypoint is missing: {entrypoint}")
        completed = subprocess.run(  # nosec B603
            [executable, "--help"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if completed.returncode != 0:
            error = completed.stderr.strip().splitlines()
            detail = error[-1] if error else f"exit {completed.returncode}"
            raise CareDependencyClosureError(
                f"CARE CLI entrypoint smoke failed: {entrypoint}: {detail}"
            )
        cli_paths[entrypoint] = executable

    report: dict[str, Any] = {
        "format_version": 1,
        "gate": "care_benchmark_dependency_closure",
        "status": "passed",
        "requirements_lock_sha256": _sha256(requirements_lock),
        "packages": package_versions,
        "imports": list(CARE_IMPORTS),
        "cli_entrypoints": list(cli_paths),
    }
    if uv_lock is not None:
        report["uv_lock_sha256"] = _sha256(uv_lock.resolve(strict=True))
    return report


def _write_report(path: Path, report: dict[str, Any]) -> None:
    if path.is_symlink():
        raise CareDependencyClosureError("closure report cannot overwrite a symbolic link")
    target = path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify the locked CARE benchmark runtime dependency closure"
    )
    parser.add_argument("--requirements-lock", type=Path, required=True)
    parser.add_argument("--uv-lock", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = verify_benchmark_dependency_closure(
            args.requirements_lock,
            uv_lock=args.uv_lock,
        )
        if args.report is not None:
            _write_report(args.report, report)
    except (CareDependencyClosureError, OSError, subprocess.SubprocessError) as exc:
        print(
            json.dumps(
                {
                    "gate": "care_benchmark_dependency_closure",
                    "status": "failed",
                    "error": str(exc),
                }
            ),
            file=__import__("sys").stderr,
        )
        raise SystemExit(2) from exc
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
