from __future__ import annotations

import base64
import os
import re
from pathlib import Path


def main() -> int:
    encoded = os.environ.get("WINDOPS_ISOLATED_RELEASE_ENV_B64", "")
    github_env = os.environ.get("GITHUB_ENV", "")
    output_path = os.environ.get("WINDOPS_RELEASE_ENV_PATH", "")
    if not encoded or not github_env or not output_path:
        raise SystemExit("protected isolated-release environment input is missing")
    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise SystemExit("isolated-release environment must be base64 UTF-8") from exc
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(decoded.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise SystemExit(f"invalid isolated-release environment line {line_number}")
        name, value = line.split("=", 1)
        if re.fullmatch(r"WINDOPS_[A-Z0-9_]+", name) is None or name in values:
            raise SystemExit(
                f"invalid or duplicate isolated-release variable on line {line_number}"
            )
        if "\x00" in value or "\r" in value or "\n" in value:
            raise SystemExit(f"isolated-release variable {name} contains a forbidden character")
        values[name] = value
    required = {
        "WINDOPS_ENVIRONMENT",
        "WINDOPS_DATABASE_URL",
        "WINDOPS_REDIS_URL",
        "WINDOPS_MINIO_ENDPOINT",
        "WINDOPS_NEO4J_URI",
        "WINDOPS_LITELLM_MODEL",
        "WINDOPS_EMBEDDING_MODEL",
    }
    missing = required - values.keys()
    if missing:
        raise SystemExit(
            "isolated-release environment is missing variables: " + ", ".join(sorted(missing))
        )
    if values["WINDOPS_ENVIRONMENT"].casefold() != "production":
        raise SystemExit("isolated-release environment must select production validation")
    reserved_identity = {
        "WINDOPS_RELEASE_ID",
        "WINDOPS_RELEASE_COMMIT_SHA",
        "WINDOPS_RELEASE_IMAGE_DIGEST",
    }
    supplied_identity = reserved_identity.intersection(values)
    if supplied_identity:
        raise SystemExit(
            "isolated-release environment cannot override candidate identity: "
            + ", ".join(sorted(supplied_identity))
        )
    environment_path = Path(output_path)
    environment_path.write_text(
        "".join(f"{name}={value}\n" for name, value in sorted(values.items())),
        encoding="utf-8",
    )
    os.chmod(environment_path, 0o600)
    with Path(github_env).open("a", encoding="utf-8", newline="\n") as stream:
        for name, value in sorted(values.items()):
            stream.write(f"{name}={value}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
