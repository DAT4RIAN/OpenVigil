"""Verify persisted software execution identities against frozen application source."""

from typing import Any

from windops_backend.config import Settings
from windops_backend.model_structural import StructuralAnalysisRun
from windops_backend.structural_contract import algorithm_identity
from windops_backend.structural_provenance import deployment_identity, execution_provenance
from windops_backend.structural_result_identity import RESULT_HASH_CONTRACT, structural_result_hash


def verify_persisted_execution(run: StructuralAnalysisRun, settings: Settings) -> dict[str, Any]:
    declared = deployment_identity(settings, "api")
    expected = algorithm_identity()
    if declared is not None:
        expected["deployment_declared"] = declared
    if run.algorithm_identity != expected or run.result is None:
        raise RuntimeError("persisted structural analysis identity differs from frozen source")
    observed = {**algorithm_identity(), "config": run.config}
    provenance = execution_provenance(declared, observed)
    if run.result.get("execution_provenance") != provenance:
        raise RuntimeError("persisted structural execution provenance differs from the real worker")
    if run.result.get("algorithm") != {**expected, "config": run.config}:
        raise RuntimeError("persisted structural calculation versions differ from frozen source")
    result = dict(run.result)
    digest = result.pop("result_sha256", None)
    if result.get(
        "result_hash_contract"
    ) != RESULT_HASH_CONTRACT or digest != structural_result_hash(result):
        raise RuntimeError(
            "persisted structural result SHA does not include its execution provenance"
        )
    return {"run_id": run.id, "result_sha256": digest, "execution_provenance": provenance}
