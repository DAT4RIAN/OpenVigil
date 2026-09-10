from __future__ import annotations

import hashlib

from windops_backend.benchmarks.care import (
    anomaly,
    contract,
    importer,
    pipeline,
    quality,
    replay,
    trust,
)
from windops_backend.benchmarks.care.artifact_utils import (
    canonical_json_bytes,
    canonical_json_sha256,
    sha256_file,
)


def test_canonical_json_utility_preserves_the_existing_permissive_contract() -> None:
    value = {"z": "风机", "a": [2, 1]}
    encoded = b'{"a":[2,1],"z":"\xe9\xa3\x8e\xe6\x9c\xba"}'
    assert canonical_json_bytes(value) == encoded
    assert canonical_json_sha256(value) == hashlib.sha256(encoded).hexdigest()
    assert canonical_json_bytes({"value": float("nan")}) == b'{"value":NaN}'


def test_existing_care_modules_delegate_to_the_shared_hash_primitives() -> None:
    assert anomaly._sha256_json is canonical_json_sha256
    assert contract._sha256_json is canonical_json_sha256
    assert importer._canonical_hash is canonical_json_sha256
    assert pipeline._sha256_json is canonical_json_sha256
    assert quality._canonical_hash is canonical_json_sha256
    assert replay._sha256_json is canonical_json_sha256
    assert trust._canonical_hash is canonical_json_sha256


def test_file_hash_is_chunk_size_independent(tmp_path) -> None:
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(bytes(range(256)) * 41)
    expected = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert sha256_file(artifact, chunk_size=17) == expected
    assert importer._sha256_file(artifact) == expected
    assert pipeline._sha256_file(artifact) == expected
