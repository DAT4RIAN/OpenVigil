from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from windops_backend.benchmarks.care.contract import (
    DATASET_VERSION,
    DOI,
    LICENSE_NAME,
    LICENSE_URL,
    ZENODO_URL,
)

CARE_DATASET_NAME = "Wind Turbine SCADA Data For Early Fault Detection"
CARE_DATASET_CREATORS = ("Christian G" + chr(0xFC) + "ck", "Cyriana M. A. Roelofs")
CARE_CREATOR_AFFILIATION = "Fraunhofer Institute for Energy Economics and Energy System Technology"
CARE_RECOMMENDED_CITATION = (
    "G" + chr(0xFC) + "ck, C.; Roelofs, C.M.A.; Faulstich, S. CARE to Compare: A Real-World "
    "Benchmark Dataset for Early Fault Detection in Wind Turbine Data. Data 2024, "
    "9, 138. https://doi.org/10.3390/data9120138"
)
CARE_ARTIFACT_LICENSE_STATEMENT = (
    "This CARE-derived data artifact is distributed under CC BY-SA 4.0; retain "
    "attribution, indicate changes, and apply ShareAlike where the license requires it."
)


def build_care_artifact_license(
    *,
    artifact_type: str,
    changes_made: str,
    source_dataset_sha256: str,
    source_artifact_sha256: str,
    transformation_versions: Mapping[str, str],
) -> dict[str, Any]:
    """Build complete, deterministic license metadata for a CARE-derived artifact."""

    if not artifact_type.strip() or not changes_made.strip():
        raise ValueError("CARE artifact type and changes_made must be non-empty")
    for label, value in (
        ("source dataset", source_dataset_sha256),
        ("source artifact", source_artifact_sha256),
    ):
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError(f"CARE {label} SHA-256 is invalid")
    versions = dict(sorted(transformation_versions.items()))
    if not versions or any(not key.strip() or not value.strip() for key, value in versions.items()):
        raise ValueError("CARE transformation versions must be non-empty")
    return {
        "dataset_name": CARE_DATASET_NAME,
        "dataset_version": DATASET_VERSION,
        "creators": list(CARE_DATASET_CREATORS),
        "creator_affiliation": CARE_CREATOR_AFFILIATION,
        "recommended_citation": CARE_RECOMMENDED_CITATION,
        "zenodo_url": ZENODO_URL,
        "doi": DOI,
        "license_name": LICENSE_NAME,
        "license_url": LICENSE_URL,
        "artifact_license": LICENSE_NAME,
        "artifact_license_statement": CARE_ARTIFACT_LICENSE_STATEMENT,
        "artifact_type": artifact_type,
        "changes_made": changes_made,
        "transformation_versions": versions,
        "source_dataset_sha256": source_dataset_sha256,
        "source_artifact_sha256": source_artifact_sha256,
        "share_alike_required": True,
        "external_distribution_review": "required",
        "code_license_is_separate": True,
    }


def verify_care_artifact_license(
    value: Mapping[str, Any],
    *,
    artifact_type: str,
    source_dataset_sha256: str,
    source_artifact_sha256: str,
    transformation_versions: Mapping[str, str],
) -> None:
    changes_made = value.get("changes_made")
    if not isinstance(changes_made, str):
        raise ValueError("CARE artifact license changes_made is invalid")
    expected = build_care_artifact_license(
        artifact_type=artifact_type,
        changes_made=changes_made,
        source_dataset_sha256=source_dataset_sha256,
        source_artifact_sha256=source_artifact_sha256,
        transformation_versions=transformation_versions,
    )
    if dict(value) != expected:
        raise ValueError("CARE artifact license metadata is incomplete or inconsistent")
