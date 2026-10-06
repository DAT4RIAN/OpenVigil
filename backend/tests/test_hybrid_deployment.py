from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml
from scripts.render_release_manifests import render_release_manifests

from test_deployment_policy import (
    COMMIT_SHA,
    IMAGE,
    IMAGE_DIGEST,
    RELEASE_ID,
    STORAGE_CLASS,
    _rendered_manifest,
    _resource,
)
from windops_backend.operations.deployment_policy import (
    DeploymentPolicyError,
    verify_deployment_policy,
)
from windops_backend.operations.hybrid_identity import hybrid_bundle_id

STRUCTURAL_DIGEST = "sha256:" + "c" * 64
STRUCTURAL_IMAGE = "registry.example/windops-structural@" + STRUCTURAL_DIGEST
OVERLAY = Path(__file__).parents[1] / "deploy/hybrid-tower"


def _documents(tmp_path: Path):
    documents = list(yaml.safe_load_all(_rendered_manifest(tmp_path).read_text()))
    for name in ("structural-worker.yaml", "network-policy.yaml"):
        for resource in yaml.safe_load_all((OVERLAY / name).read_text()):
            resource["metadata"]["namespace"] = "windops"
            documents.append(resource)
    overlay = yaml.safe_load((OVERLAY / "kustomization.yaml").read_text())
    (operation,) = yaml.safe_load(overlay["patches"][0]["patch"])
    assert operation["op"] == "replace"
    assert operation["path"] == "/spec/podSelector/matchExpressions/0/values"
    _resource(documents, "NetworkPolicy", "windops-runtime-egress")["spec"]["podSelector"][
        "matchExpressions"
    ][0]["values"] = operation["value"]
    return documents


def _render(tmp_path: Path):
    return render_release_manifests(
        _documents(tmp_path),
        release_id=RELEASE_ID,
        commit_sha=COMMIT_SHA,
        image=IMAGE,
        structural_image=STRUCTURAL_IMAGE,
    )


def _verify(tmp_path: Path, documents):
    path = tmp_path / "hybrid.yaml"
    path.write_text(yaml.safe_dump_all(documents, sort_keys=False))
    return verify_deployment_policy(
        path,
        expected_release_id=RELEASE_ID,
        expected_commit_sha=COMMIT_SHA,
        expected_image_digest=IMAGE_DIGEST,
        expected_structural_image_digest=STRUCTURAL_DIGEST,
        approved_backup_storage_class=STORAGE_CLASS,
    )


def test_hybrid_release_binds_two_images_and_preserves_general_workloads(tmp_path: Path):
    report = _verify(tmp_path, _render(tmp_path))
    assert report["bundle_id"] == hybrid_bundle_id(
        RELEASE_ID, COMMIT_SHA, IMAGE_DIGEST, STRUCTURAL_DIGEST
    )
    assert len(report["workloads"]) == 9
    for workload in report["workloads"]:
        assert workload["images"] == [
            STRUCTURAL_IMAGE if workload["name"] == "windops-structural-worker" else IMAGE
        ]


@pytest.mark.parametrize("target", ["api", "structural"])
def test_image_interchange_is_rejected(tmp_path: Path, target: str):
    documents = _render(tmp_path)
    name = "windops-api" if target == "api" else "windops-structural-worker"
    _resource(documents, "Deployment", name)["spec"]["template"]["spec"]["containers"][0][
        "image"
    ] = STRUCTURAL_IMAGE if target == "api" else IMAGE
    with pytest.raises(DeploymentPolicyError, match="approved digest"):
        _verify(tmp_path, documents)


@pytest.mark.parametrize(
    "violation",
    [
        "queue",
        "concurrency",
        "secret",
        "service_account",
        "budget",
        "label",
        "sidecar",
        "uid",
        "bundle",
        "broad_network",
        "extra_network",
        "worker_network",
        "missing_worker",
    ],
)
def test_hybrid_isolation_cannot_be_relaxed(tmp_path: Path, violation: str):
    documents = _render(tmp_path)
    worker = _resource(documents, "Deployment", "windops-structural-worker")
    pod = worker["spec"]["template"]["spec"]
    container = pod["containers"][0]
    if violation == "queue":
        container["args"][2] = "business"
    elif violation == "concurrency":
        container["args"][-1] = "4"
    elif violation == "secret":
        container["envFrom"][0]["secretRef"]["name"] = "windops-runtime"
    elif violation == "service_account":
        pod["serviceAccountName"] = "windops-runtime"
    elif violation == "budget":
        container["resources"]["limits"]["cpu"] = "8"
    elif violation == "label":
        worker["spec"]["template"]["metadata"]["labels"]["app.kubernetes.io/component"] = "worker"
    elif violation == "uid":
        pod["securityContext"]["runAsUser"] = 999
    elif violation == "sidecar":
        pod["containers"].append({**copy.deepcopy(container), "name": "other"})
    elif violation == "bundle":
        container["env"][-1]["value"] = "sha256:" + "d" * 64
    elif violation == "broad_network":
        _resource(documents, "NetworkPolicy", "windops-runtime-egress")["spec"]["podSelector"][
            "matchExpressions"
        ][0]["values"] = ["care-worker"]
    elif violation == "extra_network":
        policy = copy.deepcopy(_resource(documents, "NetworkPolicy", "windops-structural-egress"))
        policy["metadata"]["name"] = "extra-egress"
        policy["spec"]["podSelector"] = {}
        documents.append(policy)
    elif violation == "worker_network":
        _resource(documents, "NetworkPolicy", "windops-structural-egress")["spec"]["egress"][1][
            "ports"
        ].append({"protocol": "TCP", "port": 443})
    else:
        documents.remove(worker)
    with pytest.raises((DeploymentPolicyError, ValueError)):
        _verify(tmp_path, documents)


def test_renderer_refuses_single_image_for_structural_workload(tmp_path: Path):
    with pytest.raises(ValueError, match="own immutable image"):
        render_release_manifests(
            _documents(tmp_path), release_id=RELEASE_ID, commit_sha=COMMIT_SHA, image=IMAGE
        )


def test_renderer_requires_structural_workload_and_separate_digest(tmp_path: Path):
    documents = _documents(tmp_path)
    documents.remove(_resource(documents, "Deployment", "windops-structural-worker"))
    with pytest.raises(ValueError, match="requires the structural workload"):
        render_release_manifests(
            documents,
            release_id=RELEASE_ID,
            commit_sha=COMMIT_SHA,
            image=IMAGE,
            structural_image=STRUCTURAL_IMAGE,
        )
    with pytest.raises(ValueError, match="separate"):
        render_release_manifests(
            documents,
            release_id=RELEASE_ID,
            commit_sha=COMMIT_SHA,
            image=IMAGE,
            structural_image=IMAGE,
        )
