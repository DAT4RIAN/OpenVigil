from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    return subprocess.run(
        [sys.executable, "-m", "ruff", *sys.argv[1:]],
        cwd=BACKEND_ROOT,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
