import zipfile
from pathlib import Path

import pytest
import yaml
from scripts.stage_independent_release_evidence import INDEPENDENT_GATES, stage_independent_evidence

ROOT = Path(__file__).parents[2]


def test_release_pipeline_requires_both_digest_bound_images_and_final_bundle_gate():
    source = (ROOT / ".github/workflows/release.yml").read_text()
    steps = yaml.safe_load(source)["jobs"]["build-and-qualify"]["steps"]
    api = next(step for step in steps if step.get("id") == "build")
    structural = next(step for step in steps if step.get("id") == "structural-build")
    assert steps.index(api) < steps.index(structural)
    assert structural["with"]["file"] == "backend/Dockerfile.structural"
    assert (
        "BACKEND_IMAGE=${{ env.IMAGE_REPOSITORY }}@${{ steps.build.outputs.digest }}"
        in structural["with"]["build-args"]
    )
    assert structural["with"]["provenance"] == "mode=max" and structural["with"]["sbom"] is True
    scans = [
        step for step in steps if step.get("with", {}).get("output", "").endswith("image-scan.json")
    ]
    assert len(scans) == 2
    assert all(
        step["with"]["severity"] == "CRITICAL,HIGH"
        and step["with"]["ignore-unfixed"] is False
        and step["with"]["exit-code"] == "1"
        for step in scans
    )
    assert 'cosign sign --yes "${STRUCTURAL_IMAGE_REF}"' in source
    assert 'release-evidence/structural/sbom.spdx.json "${STRUCTURAL_IMAGE_REF}"' in source
    assert "subject-digest: ${{ steps.structural-build.outputs.digest }}" in source
    assert "windops_backend.operations.structural_artifact" in source
    assert "kubectl kustomize backend/deploy/hybrid-tower" in source
    assert '--expected-structural-image-digest "${STRUCTURAL_IMAGE_DIGEST}"' in source
    assert "--evidence-dir release-evidence --hybrid" in source
    final = next(
        step
        for step in steps
        if "windops_backend.operations.hybrid_release_gate" in step.get("run", "")
    )
    legacy = next(
        step
        for step in steps
        if "--qualification-output release-evidence/release-qualification.json"
        in step.get("run", "")
    )
    assert steps.index(final) > steps.index(legacy)
    assert '--api-image "${IMAGE_REF}" --structural-image "${STRUCTURAL_IMAGE_REF}"' in final["run"]
    assert (
        "--qualification-output release-evidence/hybrid-release-qualification.json" in final["run"]
    )
    assert ".api_gate_count == 11" in final["run"]


@pytest.mark.parametrize("include_structural", [False, True])
def test_hybrid_archive_cannot_silently_fall_back_to_legacy_reports(tmp_path, include_structural):
    archive = tmp_path / "reviewed.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        for gate in INDEPENDENT_GATES | ({"structural_runtime"} if include_structural else set()):
            zipped.writestr(f"reports/{gate}.json", '{"unit":"staging contract only"}')
    destination = tmp_path / "evidence"
    if include_structural:
        stage_independent_evidence(archive, destination, hybrid=True)
        assert (destination / "reports/structural_runtime.json").is_file()
    else:
        with pytest.raises(ValueError, match="structural_runtime"):
            stage_independent_evidence(archive, destination, hybrid=True)
    assert not (destination / "hybrid-release-qualification.json").exists()
