import hashlib
from pathlib import Path

from windops_backend.structural_provenance import execution_code_identity
from windops_backend.structural_result_identity import RESULT_HASH_CONTRACT

ANALYSIS_CONTRACT_VERSION = "openvigil.pyoma2-fdd.v1"
SCIENTIFIC_VERSIONS = {"pyOMA_2": "1.4.3", "numpy": "2.5.2", "scipy": "1.18.1"}


def algorithm_identity() -> dict[str, object]:
    return {
        "contract": ANALYSIS_CONTRACT_VERSION,
        "versions": dict(SCIENTIFIC_VERSIONS),
        "execution_code_sha256": execution_code_identity(),
        "result_hash_contract": RESULT_HASH_CONTRACT,
        "adapter_sha256": hashlib.sha256(
            Path(__file__).with_name("structural_analysis.py").read_bytes()
        ).hexdigest(),
    }
