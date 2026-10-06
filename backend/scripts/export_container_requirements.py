from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "requirements.container.txt"
EXPORT_ARGS = [
    "uv",
    "export",
    "--frozen",
    "--no-dev",
    "--extra",
    "connectors",
    "--extra",
    "benchmark",
    "--no-emit-project",
    "--no-annotate",
    "--no-header",
    "--format",
    "requirements.txt",
]


def export_requirements(output: Path, *, structural: bool = False) -> None:
    arguments = [*EXPORT_ARGS, "--extra", "structural"] if structural else EXPORT_ARGS
    subprocess.run(
        [*arguments, "--output-file", str(output)],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export the container dependency lock from pyproject.toml and uv.lock"
    )
    parser.add_argument(
        "--structural",
        action="store_true",
        help="export the independent structural worker dependency lock",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when requirements.container.txt is not reproducible from uv.lock",
    )
    args = parser.parse_args()
    target = ROOT / "requirements.structural.txt" if args.structural else TARGET

    if args.check:
        with tempfile.TemporaryDirectory(prefix="windops-requirements-") as directory:
            generated = Path(directory) / target.name
            export_requirements(generated, structural=args.structural)
            if generated.read_bytes() != target.read_bytes():
                raise SystemExit(
                    f"{target.name} is stale; run python scripts/export_container_requirements.py"
                    + (" --structural" if args.structural else "")
                )
        return 0

    export_requirements(target, structural=args.structural)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
