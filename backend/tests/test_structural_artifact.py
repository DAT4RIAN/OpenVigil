from __future__ import annotations

import copy
import subprocess
import sys

import pytest

from test_container_artifact import COMMIT_SHA, IMAGE, POLICY_PATH, RELEASE_ID, SOURCE_URL, _inspect
from windops_backend.operations.container_artifact import (
    ContainerArtifactError,
    load_release_policy,
)
from windops_backend.operations.structural_artifact import (
    STRUCTURAL_COMMAND,
    verify_structural_inspect,
)

STRUCTURAL_IMAGE = "ghcr.io/windops/structural@sha256:" + "c" * 64


def _images():
    policy = load_release_policy(POLICY_PATH)
    api = _inspect(policy)
    api["RootFS"] = {"Layers": ["sha256:" + "1" * 64, "sha256:" + "2" * 64]}
    structural = copy.deepcopy(api)
    structural.update(RepoDigests=[STRUCTURAL_IMAGE], Os="linux", Architecture="amd64")
    structural["RootFS"]["Layers"].append("sha256:" + "3" * 64)
    config = structural["Config"]
    config.update(
        Cmd=list(STRUCTURAL_COMMAND),
        Healthcheck={"Test": ["NONE"]},
        Env=[
            "OPENBLAS_NUM_THREADS=1",
            "OMP_NUM_THREADS=1",
            "MKL_NUM_THREADS=1",
            "MPLBACKEND=Agg",
        ],
    )
    config["Labels"]["org.opencontainers.image.base.name"] = IMAGE
    return structural, api, policy


def _verify(structural, api, policy):
    return verify_structural_inspect(
        structural,
        api,
        policy=policy,
        image=STRUCTURAL_IMAGE,
        api_image=IMAGE,
        release_id=RELEASE_ID,
        commit_sha=COMMIT_SHA,
        source_url=SOURCE_URL,
    )


def test_scientific_image_extends_exact_qualified_api_layers_and_identity():
    structural, api, policy = _images()
    verified = _verify(structural, api, policy)
    assert verified["image"] == STRUCTURAL_IMAGE and verified["api_image"] == IMAGE
    assert verified["image_digest"] != verified["api_image_digest"]
    assert verified["commit_sha"] == COMMIT_SHA


@pytest.mark.parametrize(
    "violation",
    [
        "digest",
        "parent_label",
        "source",
        "revision",
        "release",
        "uid",
        "queue",
        "concurrency",
        "entrypoint",
        "healthcheck",
        "numeric_threads",
        "layers",
        "os",
        "architecture",
        "api_cmd",
    ],
)
def test_structural_image_identity_cannot_be_substituted_or_relaxed(violation):
    structural, api, policy = _images()
    config = structural["Config"]
    if violation == "digest":
        structural["RepoDigests"] = [IMAGE]
    elif violation == "parent_label":
        config["Labels"]["org.opencontainers.image.base.name"] = "python@sha256:" + "d" * 64
    elif violation in {"source", "revision"}:
        config["Labels"]["org.opencontainers.image." + violation] = "other"
    elif violation == "release":
        config["Labels"]["org.opencontainers.image.version"] = "other"
    elif violation == "uid":
        config["User"] = "0:0"
    elif violation == "queue":
        config["Cmd"][3] = "business"
    elif violation == "concurrency":
        config["Cmd"][-1] = "8"
    elif violation == "entrypoint":
        config["Entrypoint"] = ["sh", "-c"]
    elif violation == "healthcheck":
        config["Healthcheck"] = {"Test": ["CMD", "curl", "http://localhost:8000"]}
    elif violation == "numeric_threads":
        config["Env"][0] = "OPENBLAS_NUM_THREADS=16"
    elif violation == "layers":
        structural["RootFS"]["Layers"][0] = "sha256:" + "d" * 64
    elif violation == "os":
        structural["Os"] = "windows"
    elif violation == "architecture":
        structural["Architecture"] = "arm64"
    else:
        api["Config"]["Cmd"] = ["dramatiq"]
    with pytest.raises(ContainerArtifactError):
        _verify(structural, api, policy)


def test_runtime_gate_cannot_be_disabled_by_optimized_python():
    completed = subprocess.run(
        [
            sys.executable,
            "-O",
            "-c",
            "from windops_backend.operations.structural_smoke import _require; "
            "_require(False, 'negative_runtime_guard')",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode != 0
    assert "negative_runtime_guard" in completed.stderr
