from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from windops_backend.benchmarks.care.contract import (
    DATASET_ID,
    DATASET_VERSION,
    DEFAULT_EXPLICIT_ALIASES,
    CareContractError,
    CareDatasetExpectations,
    build_care_contract,
    verify_care_contract,
)
from windops_backend.benchmarks.care.quality import (
    build_quality_contract,
    verify_quality_contract,
)

APPROVED_ROOT_SCHEMA_VERSION = "care-v6-approved-root-v1"
APPROVAL_LINEAGE_SCHEMA_VERSION = "care-v6-approved-lineage-v1"
OFFICIAL_APPROVED_ROOT_PATH = (
    Path(__file__).resolve().parent / "approved" / "care-v6-approved-root.json"
)
OFFICIAL_APPROVAL_PUBLIC_KEY_BASE64 = "WgeeMfyYhZAqV/418FzEXfzyqx+bE0BltPozBlBo9ik="


@dataclass(frozen=True, slots=True)
class CareTrustAnchor:
    approved_root: Mapping[str, Any]
    public_key_base64: str


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def canonical_source_contract(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Return the stable source semantics covered by the independent approval."""

    return {
        key: value for key, value in manifest.items() if key not in {"generator", "manifest_sha256"}
    }


def canonical_quality_policy(quality_contract: Mapping[str, Any]) -> dict[str, Any]:
    """Return quality semantics without hashes that vary with generator identity."""

    return {
        key: value
        for key, value in quality_contract.items()
        if key not in {"quality_contract_sha256", "source_manifest_sha256"}
    }


def _unsigned_approved_root(approved_root: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in approved_root.items()
        if key not in {"approved_root_sha256", "signature_base64"}
    }


def load_official_care_trust_anchor() -> CareTrustAnchor:
    try:
        value = json.loads(OFFICIAL_APPROVED_ROOT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CareContractError("official CARE approved root is unavailable or invalid") from exc
    if not isinstance(value, Mapping):
        raise CareContractError("official CARE approved root must be an object")
    return CareTrustAnchor(value, OFFICIAL_APPROVAL_PUBLIC_KEY_BASE64)


def verify_care_trust_anchor(trust_anchor: CareTrustAnchor) -> Mapping[str, Any]:
    approved_root = trust_anchor.approved_root
    if (
        approved_root.get("schema_version") != APPROVED_ROOT_SCHEMA_VERSION
        or approved_root.get("dataset_id") != DATASET_ID
        or approved_root.get("dataset_version") != DATASET_VERSION
    ):
        raise CareContractError("CARE approved root identity is invalid")

    unsigned = _unsigned_approved_root(approved_root)
    actual_root_hash = approved_root.get("approved_root_sha256")
    expected_root_hash = _canonical_hash(unsigned)
    if actual_root_hash != expected_root_hash:
        raise CareContractError(
            "CARE approved root hash mismatch: "
            f"expected {expected_root_hash}, got {actual_root_hash}"
        )

    approval = approved_root.get("approval")
    if not isinstance(approval, Mapping) or approval.get("algorithm") != "ed25519":
        raise CareContractError("CARE approved root signature policy is invalid")
    signature_base64 = approved_root.get("signature_base64")
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(trust_anchor.public_key_base64, validate=True)
        )
        signature = base64.b64decode(str(signature_base64), validate=True)
        public_key.verify(signature, _canonical_bytes(unsigned))
    except (InvalidSignature, TypeError, ValueError) as exc:
        raise CareContractError("CARE approved root signature is invalid") from exc
    return approved_root


def build_care_approval_lineage(
    manifest: Mapping[str, Any],
    quality_contract: Mapping[str, Any],
    *,
    trust_anchor: CareTrustAnchor | None = None,
) -> dict[str, Any]:
    """Verify independent root/signature and bind their identity to downstream artifacts."""

    verify_care_contract(manifest)
    verify_quality_contract(quality_contract)
    if quality_contract.get("source_manifest_sha256") != manifest.get("manifest_sha256"):
        raise CareContractError("CARE quality contract does not belong to the source manifest")

    anchor = trust_anchor or load_official_care_trust_anchor()
    approved_root = verify_care_trust_anchor(anchor)
    source = approved_root.get("source")
    quality = approved_root.get("quality")
    approval = approved_root.get("approval")
    if (
        not isinstance(source, Mapping)
        or not isinstance(quality, Mapping)
        or not isinstance(approval, Mapping)
    ):
        raise CareContractError("CARE approved root lineage is incomplete")

    source_contract_sha256 = _canonical_hash(canonical_source_contract(manifest))
    quality_policy_sha256 = _canonical_hash(canonical_quality_policy(quality_contract))
    truth_sha256 = _canonical_hash(manifest.get("events"))
    mapping_sha256 = _canonical_hash(
        {
            "mapping_contract": manifest.get("mapping_contract"),
            "farms": manifest.get("farms"),
        }
    )
    csv_files_sha256 = _canonical_hash(manifest.get("csv_files"))
    archive = source.get("archive")
    manifest_archive = manifest.get("source")
    manifest_zip = manifest_archive.get("zip") if isinstance(manifest_archive, Mapping) else None
    checks = {
        "canonical source contract": (
            source_contract_sha256,
            source.get("canonical_source_contract_sha256"),
        ),
        "source file inventory": (csv_files_sha256, source.get("csv_files_sha256")),
        "truth contract": (truth_sha256, source.get("truth_sha256")),
        "mapping contract": (mapping_sha256, source.get("mapping_sha256")),
        "quality policy": (
            quality_policy_sha256,
            quality.get("canonical_quality_policy_sha256"),
        ),
        "source archive": (
            manifest_zip,
            archive,
        ),
    }
    mismatches = [name for name, (actual, expected) in checks.items() if actual != expected]
    if mismatches:
        raise CareContractError(
            "CARE control documents do not match the independently signed approved root: "
            + ", ".join(mismatches)
        )

    signature = str(approved_root["signature_base64"])
    return {
        "schema_version": APPROVAL_LINEAGE_SCHEMA_VERSION,
        "root_id": approved_root["root_id"],
        "approved_root_sha256": approved_root["approved_root_sha256"],
        "signature_algorithm": approval["algorithm"],
        "signature_key_id": approval["key_id"],
        "signature_sha256": hashlib.sha256(base64.b64decode(signature)).hexdigest(),
        "canonical_source_contract_sha256": source_contract_sha256,
        "canonical_quality_policy_sha256": quality_policy_sha256,
        "source_manifest_sha256": manifest["manifest_sha256"],
        "quality_contract_sha256": quality_contract["quality_contract_sha256"],
        "source_archive_sha256": archive["sha256"] if isinstance(archive, Mapping) else None,
    }


def verify_embedded_care_approval(
    lineage: Mapping[str, Any],
    *,
    trust_anchor: CareTrustAnchor | None = None,
) -> None:
    """Verify an embedded lineage against a separately trusted signed root."""

    anchor = trust_anchor or load_official_care_trust_anchor()
    approved_root = verify_care_trust_anchor(anchor)
    source = approved_root.get("source")
    quality = approved_root.get("quality")
    approval = approved_root.get("approval")
    archive = source.get("archive") if isinstance(source, Mapping) else None
    if (
        not isinstance(source, Mapping)
        or not isinstance(quality, Mapping)
        or not isinstance(approval, Mapping)
        or not isinstance(archive, Mapping)
    ):
        raise CareContractError("CARE approved root lineage is incomplete")
    signature = str(approved_root["signature_base64"])
    expected = {
        "schema_version": APPROVAL_LINEAGE_SCHEMA_VERSION,
        "root_id": approved_root["root_id"],
        "approved_root_sha256": approved_root["approved_root_sha256"],
        "signature_algorithm": approval["algorithm"],
        "signature_key_id": approval["key_id"],
        "signature_sha256": hashlib.sha256(base64.b64decode(signature)).hexdigest(),
        "canonical_source_contract_sha256": source["canonical_source_contract_sha256"],
        "canonical_quality_policy_sha256": quality["canonical_quality_policy_sha256"],
        "source_archive_sha256": archive["sha256"],
    }
    if any(lineage.get(key) != value for key, value in expected.items()):
        raise CareContractError("CARE embedded lineage does not match the signed approved root")
    for field in ("source_manifest_sha256", "quality_contract_sha256"):
        value = lineage.get(field)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise CareContractError(f"CARE embedded lineage has invalid {field}")


def _approved_expectations(approved_root: Mapping[str, Any]) -> CareDatasetExpectations:
    source = approved_root.get("source")
    if not isinstance(source, Mapping):
        raise CareContractError("CARE approved root source identity is missing")
    archive = source.get("archive")
    raw = source.get("expectations")
    if not isinstance(archive, Mapping) or not isinstance(raw, Mapping):
        raise CareContractError("CARE approved root source expectations are missing")
    signal_counts = raw.get("signal_counts")
    event_ids = raw.get("event_ids")
    farms = raw.get("farms")
    if (
        not isinstance(signal_counts, Mapping)
        or not isinstance(event_ids, list)
        or not isinstance(farms, list)
    ):
        raise CareContractError("CARE approved root source expectations are malformed")
    try:
        return CareDatasetExpectations(
            farms=tuple(str(value) for value in farms),
            csv_count=int(raw["csv_count"]),
            event_ids=tuple(int(value) for value in event_ids),
            signal_counts=tuple(
                (str(farm), int(signal_counts[farm])) for farm in sorted(signal_counts)
            ),
            zip_size_bytes=int(archive["size_bytes"]),
            zip_md5=str(archive["md5"]),
            zip_sha256=str(archive["sha256"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CareContractError("CARE approved root source expectations are malformed") from exc


def verify_care_source_rebuild(
    manifest: Mapping[str, Any],
    quality_contract: Mapping[str, Any],
    dataset_root: Path,
    source_archive_path: Path | None,
    *,
    trust_anchor: CareTrustAnchor | None = None,
) -> dict[str, Any]:
    """Rebuild source and quality controls before a production write can begin."""

    anchor = trust_anchor or load_official_care_trust_anchor()
    lineage = build_care_approval_lineage(
        manifest,
        quality_contract,
        trust_anchor=anchor,
    )
    approved_root = verify_care_trust_anchor(anchor)
    approval = approved_root.get("approval")
    if not isinstance(approval, Mapping):
        raise CareContractError("CARE approved root approval policy is missing")
    if approval.get("source_rebuild_required_before_write") is not True:
        return lineage
    if source_archive_path is None:
        raise CareContractError(
            "the signed CARE approval requires the read-only source archive before writing"
        )
    generator = manifest.get("generator")
    if not isinstance(generator, Mapping):
        raise CareContractError("CARE source manifest generator identity is missing")

    rebuilt = build_care_contract(
        dataset_root,
        source_archive_path,
        expectations=_approved_expectations(approved_root),
        explicit_aliases=DEFAULT_EXPLICIT_ALIASES,
        tool_git_commit=str(generator.get("git_commit", "")),
        dependency_lock_sha256=str(generator.get("dependency_lock_sha256", "")),
    )
    if canonical_source_contract(rebuilt) != canonical_source_contract(manifest):
        raise CareContractError(
            "CARE source manifest differs from the canonical read-only source rebuild"
        )
    rebuilt_quality = build_quality_contract(rebuilt)
    if dict(rebuilt_quality) != dict(quality_contract):
        raise CareContractError(
            "CARE quality contract differs from the canonical read-only source rebuild"
        )
    return lineage


def verify_care_approval_lineage(
    lineage: Mapping[str, Any],
    manifest: Mapping[str, Any],
    quality_contract: Mapping[str, Any],
    *,
    trust_anchor: CareTrustAnchor | None = None,
) -> None:
    expected = build_care_approval_lineage(
        manifest,
        quality_contract,
        trust_anchor=trust_anchor,
    )
    if dict(lineage) != expected:
        raise CareContractError("CARE downstream artifact is not bound to the approved root")


__all__ = [
    "APPROVAL_LINEAGE_SCHEMA_VERSION",
    "APPROVED_ROOT_SCHEMA_VERSION",
    "CareTrustAnchor",
    "build_care_approval_lineage",
    "canonical_quality_policy",
    "canonical_source_contract",
    "load_official_care_trust_anchor",
    "verify_care_approval_lineage",
    "verify_embedded_care_approval",
    "verify_care_source_rebuild",
    "verify_care_trust_anchor",
]
