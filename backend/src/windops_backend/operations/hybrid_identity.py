"""Content identity of the API and dedicated structural runtime release."""

import hashlib
import re


def hybrid_bundle_id(
    release_id: str, commit_sha: str, api_digest: str, structural_digest: str
) -> str:
    if (
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,127}", release_id) is None
        or release_id.lower() in {"development", "unknown", "unreleased"}
        or "replace" in release_id.lower()
        or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit_sha) is None
        or set(commit_sha) == {"0"}
    ):
        raise ValueError("hybrid release requires an immutable release ID and full Git SHA")
    for digest in (api_digest, structural_digest):
        if re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None or digest == "sha256:" + "0" * 64:
            raise ValueError("hybrid release requires two non-placeholder SHA-256 image digests")
    if api_digest == structural_digest:
        raise ValueError("hybrid release requires separate API and structural images")
    payload = (
        f"openvigil.hybrid-release.v1\n{release_id}\n{commit_sha}\n"
        f"api={api_digest}\nstructural={structural_digest}\n"
    )
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


HYBRID_ANNOTATIONS = {
    "api_image_digest": "windops.openai.com/api-image-digest",
    "structural_image_digest": "windops.openai.com/structural-image-digest",
    "bundle_id": "windops.openai.com/release-bundle-id",
}
HYBRID_ENV = {
    "api_image_digest": "WINDOPS_API_IMAGE_DIGEST",
    "structural_image_digest": "WINDOPS_STRUCTURAL_IMAGE_DIGEST",
    "bundle_id": "WINDOPS_RELEASE_BUNDLE_ID",
}
STRUCTURAL_WORKLOAD = "windops-structural-worker"
STRUCTURAL_CONFIGURATION_RESOURCE = "windops-structural-runtime"
