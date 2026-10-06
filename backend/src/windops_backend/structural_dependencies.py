"""Validate the full structural hash lock and its immutable API-base extension."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

from packaging.markers import Marker


@dataclass(frozen=True)
class LockedDistribution:
    version: str
    hashes: frozenset[str]
    marker: str | None = None


def locked_distributions(path: Path) -> dict[str, LockedDistribution]:
    result: dict[str, LockedDistribution] = {}
    pending = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        continued = line.endswith("\\")
        pending += " " + (line[:-1].strip() if continued else line)
        if continued:
            continue
        match = re.fullmatch(
            r"\s*([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9][A-Za-z0-9.!+_-]*)"
            r"(?:\s*;\s*(.+?))?"
            r"((?:\s+--hash=sha256:[a-f0-9]{64})+)\s*",
            pending,
        )
        if match is None:
            raise ValueError("dependency lock must contain only exact pins with SHA-256 hashes")
        name = re.sub(r"[-_.]+", "-", match[1]).lower()
        if name in result:
            raise ValueError(f"duplicate locked distribution: {name}")
        result[name] = LockedDistribution(
            match[2],
            frozenset(re.findall(r"--hash=sha256:([a-f0-9]{64})", match[4])),
            str(Marker(match[3])) if match[3] else None,
        )
        pending = ""
    if pending or not result:
        raise ValueError("dependency lock is empty or has an incomplete continuation")
    return result


def dependency_delta(base: Path, structural: Path) -> str:
    base_packages = locked_distributions(base)
    structural_packages = locked_distributions(structural)
    for name, locked in base_packages.items():
        if structural_packages.get(name) != locked:
            raise ValueError(f"structural lock changes or removes the API dependency: {name}")
    added = structural_packages.keys() - base_packages.keys()
    return "".join(
        name
        + "=="
        + structural_packages[name].version
        + (
            " ; " + (structural_packages[name].marker or "")
            if structural_packages[name].marker
            else ""
        )
        + " \\\n"
        + " \\\n".join(
            "    --hash=sha256:" + value for value in sorted(structural_packages[name].hashes)
        )
        + "\n"
        for name in sorted(added)
    )


def verify_installed_lock(path: Path) -> dict[str, object]:
    locked = locked_distributions(path)
    for name, expected in locked.items():
        if expected.marker and not Marker(expected.marker).evaluate():
            continue
        installed = metadata.version(name)
        if installed != expected.version:
            raise ValueError(f"installed dependency differs from the lock: {name}")
    return {
        "requirements_lock_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "package_count": len(locked),
        "applicable_package_count": sum(
            not value.marker or Marker(value.marker).evaluate() for value in locked.values()
        ),
        "packages": {name: value.version for name, value in sorted(locked.items())},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    delta = commands.add_parser("delta")
    delta.add_argument("--base", type=Path, required=True)
    delta.add_argument("--structural", type=Path, required=True)
    delta.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--lock", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "delta":
        args.output.write_text(dependency_delta(args.base, args.structural), encoding="utf-8")
    else:
        print(json.dumps(verify_installed_lock(args.lock), sort_keys=True))


if __name__ == "__main__":
    main()
