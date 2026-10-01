from typing import Any


def trivy_image_scan(release_id: str, commit_sha: str, image_digest: str) -> dict[str, Any]:
    """A successful raw container scan, independent of the passed gate-report wrapper."""
    return {
        "SchemaVersion": 2,
        "ArtifactType": "container_image",
        "ArtifactName": f"registry.example/openvigil@{image_digest}",
        "Metadata": {
            "ImageConfig": {
                "config": {
                    "Labels": {
                        "org.opencontainers.image.version": release_id,
                        "org.opencontainers.image.revision": commit_sha,
                    }
                }
            }
        },
        "Results": [{"Target": "OpenVigil (Debian 13)", "Class": "os-pkgs", "Type": "debian"}],
    }
