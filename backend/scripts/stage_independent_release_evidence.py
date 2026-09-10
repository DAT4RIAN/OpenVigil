from __future__ import annotations

import argparse
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

INDEPENDENT_GATES = frozenset(
    {
        "migration",
        "dr_drill",
        "dast",
        "accessibility_visual",
        "slo_exercise",
        "sites_postdeploy",
    }
)
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_MEMBER_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_MEMBERS = 10_000


def stage_independent_evidence(archive: Path, evidence_dir: Path) -> None:
    if not archive.is_file() or archive.is_symlink():
        raise ValueError("independent release evidence archive is missing or unsafe")
    if archive.stat().st_size <= 0 or archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("independent release evidence archive size is invalid")
    root = evidence_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    reports_found: set[str] = set()
    total_bytes = 0
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if len(members) > MAX_MEMBERS:
            raise ValueError("independent release evidence archive has too many members")
        for member in members:
            relative = PurePosixPath(member.filename)
            if (
                relative.is_absolute()
                or not relative.parts
                or ".." in relative.parts
                or "\\" in member.filename
            ):
                raise ValueError("independent release evidence archive contains an unsafe path")
            unix_mode = member.external_attr >> 16
            if stat.S_ISLNK(unix_mode):
                raise ValueError("independent release evidence archive contains a symbolic link")
            if member.is_dir():
                continue
            if member.file_size <= 0 or member.file_size > MAX_MEMBER_BYTES:
                raise ValueError("independent release evidence archive member size is invalid")
            total_bytes += member.file_size
            if total_bytes > MAX_TOTAL_BYTES:
                raise ValueError("independent release evidence archive expands beyond its limit")
            if relative.parts[0] == "reports" and len(relative.parts) == 2:
                gate = relative.stem
                if relative.suffix != ".json" or gate not in INDEPENDENT_GATES:
                    raise ValueError("independent release evidence contains an unexpected report")
                reports_found.add(gate)
            elif relative.parts[0] != "artifacts":
                raise ValueError(
                    "independent release evidence must contain only reports and artifacts"
                )
            target = (root / Path(*relative.parts)).resolve()
            if not target.is_relative_to(root) or target.exists():
                raise ValueError(
                    "independent release evidence would escape or overwrite the bundle"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(member) as source, target.open("xb") as destination:
                shutil.copyfileobj(source, destination, length=1024 * 1024)
    missing = INDEPENDENT_GATES - reports_found
    if missing:
        raise ValueError(
            "independent release evidence is missing reports: " + ", ".join(sorted(missing))
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Safely stage independently reviewed release-gate reports and raw artifacts"
    )
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    stage_independent_evidence(args.archive, args.evidence_dir)


if __name__ == "__main__":
    main()
