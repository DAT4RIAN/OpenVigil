"""Reconstructible parse result identity, including PostgreSQL numeric JSON reads."""

from typing import Any

from windops_backend.structural_result_identity import structural_result_hash

DOCUMENT_RESULT_HASH_CONTRACT = "openvigil.document-parse-result-json.v1"


def document_parse_result_hash(result: dict[str, Any]) -> str:
    # Reuse the audited finite-number/key-order canonicalization without changing
    # the existing structural contract or any historical structural result hash.
    return structural_result_hash(result)
