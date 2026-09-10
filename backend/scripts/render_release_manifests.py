from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

WORKLOAD_KINDS = frozenset({"Deployment", "Job", "CronJob"})
REQUIRED_WORKLOADS = frozenset(
    {
        "windops-api",
        "windops-worker",
        "windops-outbox-relay",
        "windops-migrate-release",
        "windops-backup",
    }
)
RELEASE_ANNOTATIONS = {
    "release_id": "windops.openai.com/release-id",
    "commit_sha": "windops.openai.com/commit-sha",
    "image_digest": "windops.openai.com/image-digest",
}
RELEASE_ENV = {
    "release_id": "WINDOPS_RELEASE_ID",
    "commit_sha": "WINDOPS_RELEASE_COMMIT_SHA",
    "image_digest": "WINDOPS_RELEASE_IMAGE_DIGEST",
}


def _pod_template(document: dict[str, Any]) -> dict[str, Any]:
    spec = cast(dict[str, Any], document["spec"])
    if document["kind"] == "CronJob":
        return cast(dict[str, Any], spec["jobTemplate"]["spec"]["template"])
    return cast(dict[str, Any], spec["template"])


def _validate_release(release_id: str, commit_sha: str, image: str) -> str:
    if (
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,127}", release_id) is None
        or release_id.lower() in {"development", "unknown", "unreleased"}
        or "replace" in release_id.lower()
    ):
        raise ValueError("release ID must be immutable and non-placeholder")
    if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit_sha) is None:
        raise ValueError("commit SHA must be a full lowercase Git SHA")
    image_match = re.fullmatch(r"([^\s@]+)@(sha256:[0-9a-f]{64})", image)
    if image_match is None:
        raise ValueError("release image must use one immutable SHA-256 digest")
    repository, digest = image_match.groups()
    if (
        repository.startswith("registry.invalid/")
        or ":latest" in repository
        or digest == "sha256:" + "0" * 64
    ):
        raise ValueError("release image cannot use a placeholder or mutable tag")
    return digest


def render_release_manifests(
    documents: list[dict[str, Any]],
    *,
    release_id: str,
    commit_sha: str,
    image: str,
) -> list[dict[str, Any]]:
    image_digest = _validate_release(release_id, commit_sha, image)
    release = {
        "release_id": release_id,
        "commit_sha": commit_sha,
        "image_digest": image_digest,
    }
    observed: set[str] = set()
    for document in documents:
        if document.get("kind") not in WORKLOAD_KINDS:
            continue
        metadata = cast(dict[str, Any], document.get("metadata"))
        name = metadata.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("every workload requires metadata.name")
        observed.add(name)
        template = _pod_template(document)
        template_metadata = cast(dict[str, Any], template.setdefault("metadata", {}))
        for target_metadata in (metadata, template_metadata):
            annotations = cast(dict[str, str], target_metadata.setdefault("annotations", {}))
            for field, annotation in RELEASE_ANNOTATIONS.items():
                annotations[annotation] = release[field]
        pod_spec = cast(dict[str, Any], template["spec"])
        containers = cast(list[dict[str, Any]], pod_spec.get("containers"))
        if not containers:
            raise ValueError(f"{name} must contain at least one container")
        for container in containers:
            container["image"] = image
            env = cast(list[dict[str, str]], container.setdefault("env", []))
            existing = [item.get("name") for item in env]
            if len(existing) != len(set(existing)):
                raise ValueError(f"{name} contains duplicate environment variables")
            for field, variable in RELEASE_ENV.items():
                matching = [item for item in env if item.get("name") == variable]
                if matching:
                    matching[0].clear()
                    matching[0].update({"name": variable, "value": release[field]})
                else:
                    env.append({"name": variable, "value": release[field]})
    missing = REQUIRED_WORKLOADS - observed
    if missing:
        raise ValueError(f"required release workloads are missing: {', '.join(sorted(missing))}")
    return documents


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bind rendered WindOps manifests to one immutable release image"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    loaded = [
        cast(dict[str, Any], document)
        for document in yaml.safe_load_all(args.input.read_text(encoding="utf-8"))
        if document is not None
    ]
    rendered = render_release_manifests(
        loaded,
        release_id=args.release_id,
        commit_sha=args.commit_sha,
        image=args.image,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump_all(rendered, sort_keys=False),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
