from __future__ import annotations

import argparse
import configparser
import hashlib
import importlib.util
import json
import math
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path
from typing import Any

import pandas as pd

from windops_backend.benchmarks.care.scoring import (
    REFERENCE_COMMIT,
    REFERENCE_CRITICALITY_SOURCE_SHA256,
    REFERENCE_SCORE_SOURCE_SHA256,
    _reference_earliness_weights,
    build_score_protocol,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_PATH = Path("tmp/external/EnergyFaultDetector-v0.6.2")
REFERENCE_ROOT = REPOSITORY_ROOT / REFERENCE_PATH
REFERENCE_URL = "https://github.com/AEFDI/EnergyFaultDetector.git"
REFERENCE_TAG = "v0.6.2"
REFERENCE_TREE = "43c64cbe1119fb798f37d000e26657836845c912"
REFERENCE_LICENSE_SHA256 = "65f98b52eaf71a731ac8f878a0214896d63d6c0ffd4df6f486ca5e2440c2615f"
REFERENCE_FILES = {
    "energy_fault_detector/evaluation/care_score.py": REFERENCE_SCORE_SOURCE_SHA256,
    "energy_fault_detector/utils/analysis.py": REFERENCE_CRITICALITY_SOURCE_SHA256,
    "LICENSE": REFERENCE_LICENSE_SHA256,
}
SOURCE_OF_TRUTH_FILES = (
    "PRODUCT_REQUIREMENTS.md",
    "UI_UX_SPEC.md",
    "ARCHITECTURE.md",
    "AUDIT_REPORT.md",
    "UI_AUDIT_REPORT.md",
)


class CareReferenceVerificationError(RuntimeError):
    """Raised when the pinned official reference cannot prove equivalence."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_text_sha256(path: Path) -> str:
    # ``read_text`` uses universal-newline translation. Hashing the resulting
    # UTF-8 text keeps reviewed Markdown identities stable across Windows and
    # Linux checkouts without weakening the byte-exact reference-source gate.
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(REFERENCE_ROOT), *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise CareReferenceVerificationError(
            f"pinned CARE reference Git check failed: {' '.join(arguments)}"
        )
    return result.stdout.strip()


def _verify_submodule_mapping() -> None:
    modules_path = REPOSITORY_ROOT / ".gitmodules"
    if not modules_path.is_file():
        raise CareReferenceVerificationError(".gitmodules is missing")
    parser = configparser.ConfigParser()
    parser.read(modules_path, encoding="utf-8")
    section = f'submodule "{REFERENCE_PATH.as_posix()}"'
    if section not in parser:
        raise CareReferenceVerificationError("CARE reference submodule mapping is missing")
    mapping = parser[section]
    if mapping.get("path") != REFERENCE_PATH.as_posix() or mapping.get("url") != REFERENCE_URL:
        raise CareReferenceVerificationError("CARE reference submodule mapping is not canonical")


def _load_module(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise CareReferenceVerificationError(f"cannot load CARE reference module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_reference_modules() -> tuple[types.ModuleType, types.ModuleType]:
    package = types.ModuleType("energy_fault_detector")
    package.__path__ = [str(REFERENCE_ROOT / "energy_fault_detector")]  # type: ignore[attr-defined]
    sys.modules["energy_fault_detector"] = package
    utils = types.ModuleType("energy_fault_detector.utils")
    utils.__path__ = [str(REFERENCE_ROOT / "energy_fault_detector" / "utils")]  # type: ignore[attr-defined]
    sys.modules["energy_fault_detector.utils"] = utils
    deprecations = types.ModuleType("energy_fault_detector.utils._deprecations")

    def deprecate_kwargs(*_arguments: Any, **_keywords: Any) -> Any:
        def decorate(function: Any) -> Any:
            return function

        return decorate

    deprecations.deprecate_kwargs = deprecate_kwargs  # type: ignore[attr-defined]
    sys.modules["energy_fault_detector.utils._deprecations"] = deprecations
    analysis = _load_module(
        "energy_fault_detector.utils.analysis",
        REFERENCE_ROOT / "energy_fault_detector" / "utils" / "analysis.py",
    )
    care_score = _load_module(
        "energy_fault_detector.evaluation.care_score",
        REFERENCE_ROOT / "energy_fault_detector" / "evaluation" / "care_score.py",
    )
    return analysis, care_score


def _reference_vectors() -> dict[str, Any]:
    analysis, care_score = _load_reference_modules()
    earliness = []
    for positive_index in (0, 2, 3):
        prediction = pd.Series([index == positive_index for index in range(4)])
        scorer = care_score.CAREScore()
        earliness.append(float(scorer._calculate_weighted_score(prediction)))

    criticality = analysis.calculate_criticality(
        pd.Series([True, True, True, True]),
        pd.Series([True, False, False, True]),
    ).tolist()
    boundary = []
    for value in (71, 72, 73):
        scorer = care_score.CAREScore(criticality_threshold=72)
        scorer._evaluated_events = [
            {
                "event_id": 1,
                "event_label": "anomaly",
                "max_criticality": value,
                "weighted_score": 1.0,
                "f_beta_score": 1.0,
                "accuracy": 1.0,
            },
            {
                "event_id": 2,
                "event_label": "normal",
                "max_criticality": 0,
                "weighted_score": float("nan"),
                "f_beta_score": float("nan"),
                "accuracy": 1.0,
            },
        ]
        boundary.append(bool(scorer.evaluated_events.iloc[0]["anomaly_detected"]))
    return {
        "earliness_four_points": earliness,
        "criticality_status_freeze": criticality,
        "criticality_71_72_73_detected": boundary,
    }


def _windops_vectors() -> dict[str, Any]:
    protocol = build_score_protocol()
    golden = protocol["golden_vectors"]
    weights = _reference_earliness_weights(4)
    total_weight = sum(weights)
    return {
        "earliness_four_points": [weights[index] / total_weight for index in (0, 2, 3)],
        "criticality_status_freeze": golden["criticality_status_freeze"]["criticality"],
        "criticality_71_72_73_detected": golden["criticality_boundary"]["event_detected"],
    }


def verify_care_reference() -> dict[str, Any]:
    _verify_submodule_mapping()
    if not REFERENCE_ROOT.is_dir():
        raise CareReferenceVerificationError(
            "CARE reference submodule is absent; run git submodule update --init"
        )
    commit = _git("rev-parse", "HEAD")
    tree = _git("rev-parse", "HEAD^{tree}")
    tag = _git("describe", "--tags", "--exact-match", "HEAD")
    if commit != REFERENCE_COMMIT or tree != REFERENCE_TREE or tag != REFERENCE_TAG:
        raise CareReferenceVerificationError("CARE reference commit, tree, or tag is not pinned")

    file_hashes = {relative: _sha256(REFERENCE_ROOT / relative) for relative in REFERENCE_FILES}
    if file_hashes != REFERENCE_FILES:
        raise CareReferenceVerificationError("CARE reference source or license hash drifted")
    license_text = (REFERENCE_ROOT / "LICENSE").read_text(encoding="utf-8")
    if "Permission is hereby granted, free of charge" not in license_text:
        raise CareReferenceVerificationError("CARE reference MIT license text is missing")

    source_of_truth = {
        relative: _canonical_text_sha256(REPOSITORY_ROOT / relative)
        for relative in SOURCE_OF_TRUTH_FILES
    }
    official = _reference_vectors()
    windops = _windops_vectors()
    if official["criticality_status_freeze"] != windops["criticality_status_freeze"]:
        raise CareReferenceVerificationError("CARE criticality freeze comparison failed")
    if official["criticality_71_72_73_detected"] != windops["criticality_71_72_73_detected"]:
        raise CareReferenceVerificationError("CARE criticality boundary comparison failed")
    if any(
        not math.isclose(expected, actual, rel_tol=0.0, abs_tol=1e-15)
        for expected, actual in zip(
            official["earliness_four_points"],
            windops["earliness_four_points"],
            strict=True,
        )
    ):
        raise CareReferenceVerificationError("CARE earliness comparison failed")

    report: dict[str, Any] = {
        "format_version": 1,
        "gate": "care_official_reference_equivalence",
        "status": "passed",
        "reference": {
            "path": REFERENCE_PATH.as_posix(),
            "url": REFERENCE_URL,
            "tag": tag,
            "commit": commit,
            "tree": tree,
            "license": "MIT",
            "file_sha256": file_hashes,
        },
        "source_of_truth_sha256": source_of_truth,
        "comparison": official,
    }
    report["evidence_root_sha256"] = _canonical_hash(report)
    return report


def _write_report(path: Path, report: dict[str, Any]) -> None:
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
    parser = argparse.ArgumentParser(description="Verify the pinned official CARE reference")
    parser.add_argument("--report", type=Path)
    arguments = parser.parse_args()
    try:
        report = verify_care_reference()
        if arguments.report is not None:
            _write_report(arguments.report, report)
    except (CareReferenceVerificationError, OSError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}), file=sys.stderr)
        raise SystemExit(2) from exc
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
