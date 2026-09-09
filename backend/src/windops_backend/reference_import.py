from __future__ import annotations

import argparse
import asyncio
import getpass
from hmac import compare_digest

from windops_backend.config import get_settings
from windops_backend.db import create_engine, create_session_factory
from windops_backend.services.seed import seed_wt023_demo


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Explicitly import the controlled WT-023 reference-data pack."
    )
    parser.add_argument("--reference-pack", choices=["wt023"], required=True)
    args = parser.parse_args()
    supplied = getpass.getpass("Operations-manager API key: ")
    settings = get_settings()
    if not compare_digest(supplied, settings.operations_manager_api_key.get_secret_value()):
        raise SystemExit("reference import authentication failed")
    asyncio.run(_import_reference_pack(args.reference_pack))


async def _import_reference_pack(reference_pack: str) -> None:
    if reference_pack != "wt023":  # pragma: no cover - argparse constrains this
        raise ValueError("unsupported reference pack")
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            # Master/reference entities only: no workflow instance is pre-created.
            await seed_wt023_demo(session)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    main()
