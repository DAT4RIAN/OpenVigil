from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from windops_backend.benchmarks.care.trust import (
    APPROVED_ROOT_SCHEMA_VERSION,
    CareTrustAnchor,
    canonical_quality_policy,
    canonical_source_contract,
)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def make_test_trust_anchor(
    manifest: Mapping[str, Any],
    quality_contract: Mapping[str, Any],
    *,
    root_id: str = "care-v6-test-root",
) -> CareTrustAnchor:
    """Issue an ephemeral test-only root; production code never owns its private key."""

    source = manifest["source"]
    archive = source["zip"]
    farms = [str(farm["farm"]) for farm in manifest.get("farms", [])]
    events = [int(event["event_id"]) for event in manifest.get("events", [])]
    signal_counts = {
        str(farm["farm"]): int(farm["signal_column_count"]) for farm in manifest.get("farms", [])
    }
    unsigned: dict[str, Any] = {
        "schema_version": APPROVED_ROOT_SCHEMA_VERSION,
        "root_id": root_id,
        "dataset_id": "care",
        "dataset_version": "v6",
        "source": {
            "doi": source["doi"],
            "zenodo_url": source["zenodo_url"],
            "archive": dict(archive),
            "expectations": {
                "farms": farms,
                "csv_count": int(manifest["summary"]["csv_file_count"]),
                "event_ids": events,
                "signal_counts": signal_counts,
            },
            "canonical_source_contract_sha256": _canonical_hash(
                canonical_source_contract(manifest)
            ),
            "csv_files_sha256": _canonical_hash(manifest.get("csv_files")),
            "truth_sha256": _canonical_hash(manifest.get("events")),
            "mapping_sha256": _canonical_hash(
                {
                    "mapping_contract": manifest.get("mapping_contract"),
                    "farms": manifest.get("farms"),
                }
            ),
        },
        "quality": {
            "quality_contract_version": quality_contract["quality_contract_version"],
            "quality_rule_version": quality_contract["quality_rule_version"],
            "feature_set_version": quality_contract["feature_set_version"],
            "canonical_quality_policy_sha256": _canonical_hash(
                canonical_quality_policy(quality_contract)
            ),
        },
        "approval": {
            "algorithm": "ed25519",
            "key_id": "ephemeral-pytest-only",
            "issued_at": "2026-09-04T00:00:00Z",
            "source_rebuild_required_before_write": False,
        },
    }
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    canonical = _canonical_bytes(unsigned)
    approved_root = {
        **unsigned,
        "approved_root_sha256": hashlib.sha256(canonical).hexdigest(),
        "signature_base64": base64.b64encode(private_key.sign(canonical)).decode("ascii"),
    }
    return CareTrustAnchor(
        approved_root=approved_root,
        public_key_base64=base64.b64encode(public_key).decode("ascii"),
    )


__all__ = ["make_test_trust_anchor"]
