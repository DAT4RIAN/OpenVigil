"""Reject API-base drift while preserving every structural dependency hash."""

from pathlib import Path

import pytest

from windops_backend import structural_dependencies as dependencies

HASH_A = "a" * 64
HASH_B = "b" * 64


def lock(tmp_path, name, contents):
    path = tmp_path / name
    path.write_text(contents, encoding="utf-8")
    return path


def test_actual_structural_delta_retains_hashes_and_full_api_closure(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    base = backend / "requirements.container.txt"
    full = backend / "requirements.structural.txt"
    delta = lock(tmp_path, "delta.txt", dependencies.dependency_delta(base, full))
    added = dependencies.locked_distributions(delta)
    assert set(added) == {"et-xmlfile", "openpyxl", "pandas", "pyoma-2", "tzdata"}
    assert {
        **dependencies.locked_distributions(base),
        **added,
    } == dependencies.locked_distributions(full)


@pytest.mark.parametrize(
    "contents",
    [
        "pkg>=1.0 --hash=sha256:" + HASH_A,
        "pkg==1.0",
        "pkg==1.0 --hash=sha256:short",
        "pkg @ https://example.test/pkg.whl --hash=sha256:" + HASH_A,
        "pkg==1.0; unsupported_platform > '3.0' --hash=sha256:" + HASH_A,
        "--extra-index-url https://example.test/simple",
        "pkg==1.0 --hash=sha256:" + HASH_A + " \\\n",
        "pkg_name==1.0 --hash=sha256:" + HASH_A + "\npkg-name==1.0 --hash=sha256:" + HASH_A,
        "# empty lock\n",
    ],
)
def test_lock_rejects_unpinned_unsupported_and_duplicate_inputs(tmp_path, contents):
    with pytest.raises(ValueError):
        dependencies.locked_distributions(lock(tmp_path, "bad.txt", contents))


@pytest.mark.parametrize("changed", ["version", "hash", "removed", "marker"])
def test_delta_cannot_replace_or_remove_immutable_api_dependency(tmp_path, changed):
    base = lock(tmp_path, "base.txt", "pkg==1.0 --hash=sha256:" + HASH_A)
    structural = "added==2.0 --hash=sha256:" + HASH_B + "\n"
    if changed != "removed":
        structural += (
            "pkg=="
            + ("2.0" if changed == "version" else "1.0")
            + (" ; sys_platform == 'win32'" if changed == "marker" else "")
            + " --hash=sha256:"
            + (HASH_B if changed == "hash" else HASH_A)
        )
    with pytest.raises(ValueError, match="changes or removes"):
        dependencies.dependency_delta(base, lock(tmp_path, "full.txt", structural))


def test_installed_version_mismatch_is_not_accepted(tmp_path, monkeypatch):
    path = lock(tmp_path, "full.txt", "pkg==1.0 --hash=sha256:" + HASH_A)
    monkeypatch.setattr(dependencies.metadata, "version", lambda name: "2.0")
    with pytest.raises(ValueError, match="differs from the lock"):
        dependencies.verify_installed_lock(path)


def test_missing_dependency_is_not_accepted(tmp_path, monkeypatch):
    path = lock(tmp_path, "full.txt", "pkg==1.0 --hash=sha256:" + HASH_A)

    def missing(name):
        raise dependencies.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(dependencies.metadata, "version", missing)
    with pytest.raises(dependencies.metadata.PackageNotFoundError):
        dependencies.verify_installed_lock(path)
