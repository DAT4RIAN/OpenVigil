from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import windops_backend.operations.backups as backups
import windops_backend.operations.care_execution_plane as care_execution_plane
import windops_backend.operations.care_fullscale_acceptance as care_fullscale_acceptance
import windops_backend.operations.deployment_policy as deployment_policy
import windops_backend.operations.release_gate as release_gate
import windops_backend.operations.report_io as report_io


class ReportOutputError(ValueError):
    pass


def test_sha256_file_matches_streaming_golden_and_legacy_exports(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.bin"
    payload = bytes(range(256)) * 8193
    artifact.write_bytes(payload)

    expected = hashlib.sha256(payload).hexdigest()
    assert report_io.sha256_file(artifact, chunk_size=257) == expected
    assert backups.sha256_file is report_io.sha256_file
    assert care_execution_plane._sha256 is report_io.sha256_file
    assert care_fullscale_acceptance._sha256 is report_io.sha256_file
    assert deployment_policy._sha256 is report_io.sha256_file
    assert release_gate._sha256_file is report_io.sha256_file


def test_atomic_json_has_stable_bytes_replaces_target_and_cleans_tempfiles(
    tmp_path: Path,
) -> None:
    target = tmp_path / "nested" / "report.json"
    target.parent.mkdir()
    target.write_text("stale", encoding="utf-8")

    report_io.write_atomic_json(
        target,
        {"z": [2, 1], "a": "wind"},
        symlink_error=ReportOutputError("must not follow symlink"),
        temporary_suffix=".tmp",
    )

    assert target.read_bytes() == b'{\n  "a": "wind",\n  "z": [\n    2,\n    1\n  ]\n}\n'
    assert list(target.parent.glob(f".{target.name}.*")) == []


def test_atomic_json_rejects_symlink_before_resolving_or_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "report.json"
    monkeypatch.setattr(Path, "is_symlink", lambda _path: True)

    with pytest.raises(ReportOutputError, match="must not follow symlink"):
        report_io.write_atomic_json(
            target,
            {"status": "verified"},
            symlink_error=ReportOutputError("must not follow symlink"),
        )

    assert not target.exists()


def test_operation_report_implementations_are_not_duplicated() -> None:
    operations_root = Path(__file__).parents[1] / "src" / "windops_backend" / "operations"
    sources = {path.name: path.read_text(encoding="utf-8") for path in operations_root.glob("*.py")}
    assert [name for name, source in sources.items() if "tempfile.mkstemp" in source] == [
        "report_io.py"
    ]
    assert [name for name, source in sources.items() if "json.dump(" in source] == ["report_io.py"]
