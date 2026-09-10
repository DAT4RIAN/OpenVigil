from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from scripts.render_release_manifests import render_release_manifests

from windops_backend.operations.deployment_policy import (
    DeploymentPolicyError,
    main,
)
from windops_backend.operations.deployment_policy import (
    verify_deployment_policy as _verify_deployment_policy,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_ROOT = BACKEND_ROOT / "deploy" / "kubernetes"
IMAGE_DIGEST = "sha256:" + "b" * 64
IMAGE = f"registry.example/windops-backend@{IMAGE_DIGEST}"
RELEASE_ID = "windops-2026.08.19-rc1"
COMMIT_SHA = "a" * 40
STORAGE_CLASS = "windops-encrypted-backup"
NAMESPACED_KINDS = {
    "ServiceAccount",
    "Service",
    "Deployment",
    "Job",
    "CronJob",
    "PersistentVolumeClaim",
    "PodDisruptionBudget",
    "HorizontalPodAutoscaler",
    "NetworkPolicy",
}


def _rendered_manifest(
    tmp_path: Path,
    mutate: Callable[[list[dict[str, Any]]], None] | None = None,
) -> Path:
    documents: list[dict[str, Any]] = []
    for path in sorted(DEPLOY_ROOT.glob("*.yaml")):
        if path.name == "kustomization.yaml":
            continue
        for loaded in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if not isinstance(loaded, dict) or "kind" not in loaded:
                continue
            document = cast(dict[str, Any], loaded)
            metadata = cast(dict[str, Any], document["metadata"])
            if document["kind"] in NAMESPACED_KINDS:
                metadata["namespace"] = "windops"
            if document["kind"] in {"Deployment", "Job", "CronJob"}:
                spec = cast(dict[str, Any], document["spec"])
                pod_spec = (
                    spec["jobTemplate"]["spec"]["template"]["spec"]
                    if document["kind"] == "CronJob"
                    else spec["template"]["spec"]
                )
                for container in pod_spec["containers"]:
                    repository = container["image"].split("@", 1)[0]
                    container["image"] = f"{repository}@{IMAGE_DIGEST}"
            documents.append(document)
    documents = render_release_manifests(
        documents,
        release_id=RELEASE_ID,
        commit_sha=COMMIT_SHA,
        image=IMAGE,
    )
    if mutate:
        mutate(documents)
    rendered = tmp_path / "rendered.yaml"
    rendered.write_text(yaml.safe_dump_all(documents, sort_keys=False), encoding="utf-8")
    return rendered


def verify_deployment_policy(
    manifests: Path,
    *,
    expected_image_digest: str,
    approved_backup_storage_class: str,
) -> dict[str, Any]:
    return _verify_deployment_policy(
        manifests,
        expected_image_digest=expected_image_digest,
        expected_release_id=RELEASE_ID,
        expected_commit_sha=COMMIT_SHA,
        approved_backup_storage_class=approved_backup_storage_class,
    )


def _resource(documents: list[dict[str, Any]], kind: str, name: str) -> dict[str, Any]:
    return next(
        document
        for document in documents
        if document["kind"] == kind and document["metadata"]["name"] == name
    )


def test_rendered_production_manifests_emit_machine_verifiable_evidence(tmp_path: Path) -> None:
    rendered = _rendered_manifest(tmp_path)

    report = verify_deployment_policy(
        rendered,
        expected_image_digest=IMAGE_DIGEST,
        approved_backup_storage_class=STORAGE_CLASS,
    )

    assert report["gate"] == "deployment_policy"
    assert report["status"] == "passed"
    assert report["expected_image_digest"] == IMAGE_DIGEST
    assert report["expected_release_id"] == RELEASE_ID
    assert report["expected_commit_sha"] == COMMIT_SHA
    assert report["approved_backup_storage_class"] == STORAGE_CLASS
    assert report["resource_count"] == 14
    assert {workload["name"] for workload in report["workloads"]} == {
        "windops-api",
        "windops-worker",
        "windops-outbox-relay",
        "windops-migrate-release",
        "windops-backup",
    }
    assert report["manifest_files"] == [
        {"name": "rendered.yaml", "sha256": report["manifest_files"][0]["sha256"]}
    ]
    assert len(report["manifest_files"][0]["sha256"]) == 64


def test_policy_rejects_release_identity_drift_between_workloads(tmp_path: Path) -> None:
    def drift_worker(documents: list[dict[str, Any]]) -> None:
        worker = _resource(documents, "Deployment", "windops-worker")
        template = worker["spec"]["template"]
        template["metadata"]["annotations"]["windops.openai.com/commit-sha"] = "c" * 40
        for item in template["spec"]["containers"][0]["env"]:
            if item["name"] == "WINDOPS_RELEASE_IMAGE_DIGEST":
                item["value"] = "sha256:" + "c" * 64

    rendered = _rendered_manifest(tmp_path, drift_worker)
    with pytest.raises(DeploymentPolicyError, match="approved release"):
        verify_deployment_policy(
            rendered,
            expected_image_digest=IMAGE_DIGEST,
            approved_backup_storage_class=STORAGE_CLASS,
        )


@pytest.mark.parametrize(
    ("digest", "storage_class", "message"),
    [
        ("sha256:" + "0" * 64, STORAGE_CLASS, "non-placeholder"),
        ("sha256:invalid", STORAGE_CLASS, "non-placeholder"),
        (IMAGE_DIGEST, "standard", "encrypted backup storage class"),
    ],
)
def test_policy_rejects_placeholder_inputs(
    tmp_path: Path,
    digest: str,
    storage_class: str,
    message: str,
) -> None:
    rendered = _rendered_manifest(tmp_path)
    with pytest.raises(DeploymentPolicyError, match=message):
        verify_deployment_policy(
            rendered,
            expected_image_digest=digest,
            approved_backup_storage_class=storage_class,
        )


def test_policy_rejects_unapproved_images_and_embedded_secrets(tmp_path: Path) -> None:
    def mutate(documents: list[dict[str, Any]]) -> None:
        api = _resource(documents, "Deployment", "windops-api")
        api["spec"]["template"]["spec"]["containers"][0]["image"] = (
            "registry.example/windops-backend@sha256:" + "c" * 64
        )

    rendered = _rendered_manifest(tmp_path, mutate)
    with pytest.raises(DeploymentPolicyError, match="approved digest"):
        verify_deployment_policy(
            rendered,
            expected_image_digest=IMAGE_DIGEST,
            approved_backup_storage_class=STORAGE_CLASS,
        )

    def add_secret(documents: list[dict[str, Any]]) -> None:
        documents.append(
            {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {"name": "forbidden", "namespace": "windops"},
                "stringData": {"password": "must-never-be-rendered"},
            }
        )

    rendered = _rendered_manifest(tmp_path, add_secret)
    with pytest.raises(DeploymentPolicyError, match="cannot contain Secret"):
        verify_deployment_policy(
            rendered,
            expected_image_digest=IMAGE_DIGEST,
            approved_backup_storage_class=STORAGE_CLASS,
        )


def test_policy_rejects_root_workloads_and_destinationless_egress(tmp_path: Path) -> None:
    def root_api(documents: list[dict[str, Any]]) -> None:
        api = _resource(documents, "Deployment", "windops-api")
        api["spec"]["template"]["spec"]["securityContext"]["runAsUser"] = 0

    rendered = _rendered_manifest(tmp_path, root_api)
    with pytest.raises(DeploymentPolicyError, match="positive numeric ID"):
        verify_deployment_policy(
            rendered,
            expected_image_digest=IMAGE_DIGEST,
            approved_backup_storage_class=STORAGE_CLASS,
        )

    def broad_egress(documents: list[dict[str, Any]]) -> None:
        policy = _resource(documents, "NetworkPolicy", "windops-runtime-egress")
        policy["spec"]["egress"][1].pop("to")

    rendered = _rendered_manifest(tmp_path, broad_egress)
    with pytest.raises(DeploymentPolicyError, match="explicit destination"):
        verify_deployment_policy(
            rendered,
            expected_image_digest=IMAGE_DIGEST,
            approved_backup_storage_class=STORAGE_CLASS,
        )


@pytest.mark.parametrize(
    ("peer", "message"),
    [
        ({}, "constrain a namespace"),
        ({"namespaceSelector": {"matchLabels": {}}}, "select every target"),
        ({"ipBlock": {"cidr": "0.0.0.0/0"}}, "too broad"),
    ],
)
def test_policy_rejects_egress_peers_that_only_look_constrained(
    tmp_path: Path,
    peer: dict[str, Any],
    message: str,
) -> None:
    def broad_peer(documents: list[dict[str, Any]]) -> None:
        policy = _resource(documents, "NetworkPolicy", "windops-runtime-egress")
        policy["spec"]["egress"][1]["to"] = [peer]

    rendered = _rendered_manifest(tmp_path, broad_peer)
    with pytest.raises(DeploymentPolicyError, match=message):
        verify_deployment_policy(
            rendered,
            expected_image_digest=IMAGE_DIGEST,
            approved_backup_storage_class=STORAGE_CLASS,
        )


def test_policy_rejects_default_deny_allow_rules_and_port_ranges(tmp_path: Path) -> None:
    def allow_everything(documents: list[dict[str, Any]]) -> None:
        policy = _resource(documents, "NetworkPolicy", "windops-default-deny")
        policy["spec"]["egress"] = [{}]

    rendered = _rendered_manifest(tmp_path, allow_everything)
    with pytest.raises(DeploymentPolicyError, match="deny all ingress and egress"):
        verify_deployment_policy(
            rendered,
            expected_image_digest=IMAGE_DIGEST,
            approved_backup_storage_class=STORAGE_CLASS,
        )

    def port_range(documents: list[dict[str, Any]]) -> None:
        policy = _resource(documents, "NetworkPolicy", "windops-runtime-egress")
        policy["spec"]["egress"][1]["ports"][0]["endPort"] = 65535

    rendered = _rendered_manifest(tmp_path, port_range)
    with pytest.raises(DeploymentPolicyError, match="port ranges"):
        verify_deployment_policy(
            rendered,
            expected_image_digest=IMAGE_DIGEST,
            approved_backup_storage_class=STORAGE_CLASS,
        )


def test_policy_requires_rendered_namespace_and_approved_backup_class(tmp_path: Path) -> None:
    def wrong_namespace(documents: list[dict[str, Any]]) -> None:
        _resource(documents, "Service", "windops-api")["metadata"]["namespace"] = "default"

    rendered = _rendered_manifest(tmp_path, wrong_namespace)
    with pytest.raises(DeploymentPolicyError, match="namespace windops"):
        verify_deployment_policy(
            rendered,
            expected_image_digest=IMAGE_DIGEST,
            approved_backup_storage_class=STORAGE_CLASS,
        )

    def wrong_storage(documents: list[dict[str, Any]]) -> None:
        _resource(documents, "PersistentVolumeClaim", "windops-backups")["spec"][
            "storageClassName"
        ] = "unencrypted-storage"

    rendered = _rendered_manifest(tmp_path, wrong_storage)
    with pytest.raises(DeploymentPolicyError, match="approved encrypted storage"):
        verify_deployment_policy(
            rendered,
            expected_image_digest=IMAGE_DIGEST,
            approved_backup_storage_class=STORAGE_CLASS,
        )


def test_cli_writes_the_exact_report_used_for_release_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rendered = _rendered_manifest(tmp_path)
    report_path = tmp_path / "evidence" / "deployment-policy.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "windops-deployment-policy",
            "--manifests",
            str(rendered),
            "--expected-image-digest",
            IMAGE_DIGEST,
            "--expected-release-id",
            RELEASE_ID,
            "--expected-commit-sha",
            COMMIT_SHA,
            "--approved-backup-storage-class",
            STORAGE_CLASS,
            "--report",
            str(report_path),
        ],
    )

    main()

    stdout_report = json.loads(capsys.readouterr().out)
    file_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert stdout_report == file_report
    assert file_report["status"] == "passed"


def test_cli_emits_structured_failure_without_a_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rendered = _rendered_manifest(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "windops-deployment-policy",
            "--manifests",
            str(rendered),
            "--expected-image-digest",
            "sha256:" + "0" * 64,
            "--expected-release-id",
            RELEASE_ID,
            "--expected-commit-sha",
            COMMIT_SHA,
            "--approved-backup-storage-class",
            STORAGE_CLASS,
        ],
    )

    with pytest.raises(SystemExit, match="2"):
        main()

    captured = capsys.readouterr()
    assert captured.out == ""
    failure = json.loads(captured.err)
    assert failure["gate"] == "deployment_policy"
    assert failure["status"] == "failed"
    assert "non-placeholder" in failure["error"]
