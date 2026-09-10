from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

EXPECTED_HEAD = "0026_schema_contract_alignment"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
DECLARATION_FILES = (
    REPOSITORY_ROOT / "README.md",
    REPOSITORY_ROOT / "docs" / "runbooks" / "release-acceptance.md",
    BACKEND_ROOT / "deploy" / "README.md",
    REPOSITORY_ROOT / "docs" / "demo-gap-audit.md",
)


def verify_migration_head() -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    heads = tuple(script.get_heads())
    if heads != (EXPECTED_HEAD,):
        raise SystemExit(
            f"expected one Alembic head {EXPECTED_HEAD}, found {', '.join(heads) or 'none'}"
        )
    for declaration_file in DECLARATION_FILES:
        content = declaration_file.read_text(encoding="utf-8")
        if EXPECTED_HEAD not in content:
            raise SystemExit(
                f"{declaration_file.relative_to(REPOSITORY_ROOT)} does not declare {EXPECTED_HEAD}"
            )


if __name__ == "__main__":
    verify_migration_head()
    print(f"Alembic unique head verified: {EXPECTED_HEAD}")
