from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from scripts import verify_care_reference


@pytest.mark.parametrize(
    "index_record",
    [
        "",
        (
            "100644 a338b6efb3a650536930c6e67247694071d2f63e 0"
            "\ttmp/external/EnergyFaultDetector-v0.6.2\n"
        ),
        (
            "160000 0000000000000000000000000000000000000000 0"
            "\ttmp/external/EnergyFaultDetector-v0.6.2\n"
        ),
    ],
)
def test_local_reference_clone_cannot_replace_the_pinned_gitlink(
    monkeypatch: pytest.MonkeyPatch,
    index_record: str,
) -> None:
    monkeypatch.setattr(
        verify_care_reference.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout=index_record, stderr=""
        ),
    )

    with pytest.raises(
        verify_care_reference.CareReferenceVerificationError,
        match="gitlink is missing or is not pinned",
    ):
        verify_care_reference._verify_superproject_gitlink()


def test_pinned_official_care_reference_is_reproducible(tmp_path: Path) -> None:
    backend_root = Path(__file__).resolve().parents[1]
    report_path = tmp_path / "care-reference-evidence.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/verify_care_reference.py",
            "--report",
            str(report_path),
        ],
        cwd=backend_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert report["reference"] == {
        "path": "tmp/external/EnergyFaultDetector-v0.6.2",
        "url": "https://github.com/AEFDI/EnergyFaultDetector.git",
        "tag": "v0.6.2",
        "commit": "a338b6efb3a650536930c6e67247694071d2f63e",
        "tree": "43c64cbe1119fb798f37d000e26657836845c912",
        "license": "MIT",
        "file_sha256": {
            "LICENSE": "65f98b52eaf71a731ac8f878a0214896d63d6c0ffd4df6f486ca5e2440c2615f",
            "energy_fault_detector/evaluation/care_score.py": (
                "122eaf43c5f6703b78e89a4273ad236ddb7b99f7598dcc44bc808e9476285078"
            ),
            "energy_fault_detector/utils/analysis.py": (
                "2d593ef0474e5d38dd2cbca03fcf1de9f300f764c6305799c48b168481fb558e"
            ),
        },
    }
    assert report["comparison"] == {
        "earliness_four_points": [
            0.3488372093023256,
            0.21705426356589147,
            0.09302325581395347,
        ],
        "criticality_status_freeze": [1, 1, 1, 2],
        "criticality_71_72_73_detected": [False, True, True],
    }
    assert set(report["source_of_truth_sha256"]) == {
        "PRODUCT_REQUIREMENTS.md",
        "UI_UX_SPEC.md",
        "ARCHITECTURE.md",
        "AUDIT_REPORT.md",
        "UI_AUDIT_REPORT.md",
    }
    repository_root = backend_root.parent
    assert report["source_of_truth_sha256"] == {
        relative: hashlib.sha256(
            (repository_root / relative).read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest()
        for relative in report["source_of_truth_sha256"]
    }
    assert len(report["evidence_root_sha256"]) == 64
