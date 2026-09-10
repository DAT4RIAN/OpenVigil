from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

from windops_backend.operations.report_io import sha256_file as _sha256
from windops_backend.operations.report_io import write_atomic_json

PLACEHOLDER_DIGEST = "sha256:" + "0" * 64
EXPECTED_NAMESPACE = "windops"
RUNTIME_CONFIGURATION_RESOURCE = "windops-runtime"
RUNTIME_SERVICE_ACCOUNT = "windops-runtime"
CARE_CONFIGURATION_RESOURCE = "windops-care-runtime"
CARE_SERVICE_ACCOUNT = "windops-care-worker"
CARE_WORKLOAD = "windops-care-full-scale"
REQUIRED_RESOURCE_IDENTITIES = frozenset(
    {
        ("Namespace", "windops"),
        ("ServiceAccount", "windops-runtime"),
        ("ServiceAccount", "windops-care-worker"),
        ("Service", "windops-api"),
        ("Deployment", "windops-api"),
        ("Deployment", "windops-worker"),
        ("Deployment", "windops-outbox-relay"),
        ("Deployment", "windops-read-audit-worker"),
        ("Job", "windops-migrate-release"),
        ("CronJob", "windops-backup"),
        ("CronJob", "windops-read-audit-maintenance"),
        ("CronJob", "windops-care-full-scale"),
        ("PersistentVolumeClaim", "windops-backups"),
        ("PersistentVolumeClaim", "windops-care-source"),
        ("PersistentVolumeClaim", "windops-care-workspace"),
        ("PodDisruptionBudget", "windops-api"),
        ("HorizontalPodAutoscaler", "windops-api"),
        ("NetworkPolicy", "windops-default-deny"),
        ("NetworkPolicy", "windops-api-ingress"),
        ("NetworkPolicy", "windops-runtime-egress"),
        ("NetworkPolicy", "windops-care-egress"),
    }
)
WORKLOAD_KINDS = frozenset({"Deployment", "Job", "CronJob"})
CLUSTER_SCOPED_KINDS = frozenset({"Namespace"})
REQUIRED_RESOURCE_KEYS = frozenset({"cpu", "memory", "ephemeral-storage"})
RELEASE_ANNOTATIONS = {
    "release_id": "windops.openai.com/release-id",
    "commit_sha": "windops.openai.com/commit-sha",
    "image_digest": "windops.openai.com/image-digest",
}
RELEASE_ENV = {
    "release_id": "WINDOPS_RELEASE_ID",
    "commit_sha": "WINDOPS_RELEASE_COMMIT_SHA",
    "image_digest": "WINDOPS_RELEASE_IMAGE_DIGEST",
}


class DeploymentPolicyError(ValueError):
    """Raised when rendered deployment manifests violate the OpenVigil policy."""


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DeploymentPolicyError(f"{field} must be a mapping")
    return cast(dict[str, Any], value)


def _sequence(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise DeploymentPolicyError(f"{field} must be a list")
    return value


def _manifest_paths(manifests: Path) -> list[Path]:
    root = manifests.resolve()
    if manifests.is_symlink():
        raise DeploymentPolicyError("manifest input cannot be a symbolic link")
    if root.is_file():
        paths = [root]
    elif root.is_dir():
        paths = sorted((*root.glob("*.yaml"), *root.glob("*.yml")))
    else:
        raise DeploymentPolicyError("manifest input does not exist")
    if not paths:
        raise DeploymentPolicyError("manifest input contains no YAML files")
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise DeploymentPolicyError("manifest files must be regular files, not symlinks")
    return paths


def _documents(manifests: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    documents: list[dict[str, Any]] = []
    files: list[dict[str, str]] = []
    identities: set[tuple[str, str]] = set()
    for path in _manifest_paths(manifests):
        files.append({"name": path.name, "sha256": _sha256(path)})
        try:
            loaded_documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        except yaml.YAMLError as exc:
            raise DeploymentPolicyError(f"invalid YAML in {path.name}") from exc
        for index, loaded in enumerate(loaded_documents, start=1):
            if loaded is None:
                continue
            document = _mapping(loaded, f"{path.name} document {index}")
            if document.get("kind") == "List":
                candidates = _sequence(document.get("items"), f"{path.name} List.items")
            else:
                candidates = [document]
            for candidate_index, candidate in enumerate(candidates, start=1):
                resource = _mapping(candidate, f"{path.name} resource {candidate_index}")
                kind = resource.get("kind")
                api_version = resource.get("apiVersion")
                metadata = _mapping(resource.get("metadata"), f"{path.name} metadata")
                name = metadata.get("name")
                if not isinstance(kind, str) or not isinstance(api_version, str):
                    raise DeploymentPolicyError("every resource requires kind and apiVersion")
                if not isinstance(name, str) or not name:
                    raise DeploymentPolicyError("every resource requires metadata.name")
                identity = (kind, name)
                if identity in identities:
                    raise DeploymentPolicyError(f"duplicate rendered resource: {kind}/{name}")
                identities.add(identity)
                if (
                    kind not in CLUSTER_SCOPED_KINDS
                    and metadata.get("namespace") != EXPECTED_NAMESPACE
                ):
                    raise DeploymentPolicyError(
                        f"{kind}/{name} must be rendered into namespace {EXPECTED_NAMESPACE}"
                    )
                documents.append(resource)
    return documents, files


def _named(documents: list[dict[str, Any]], kind: str, name: str) -> dict[str, Any]:
    try:
        return next(
            resource
            for resource in documents
            if resource.get("kind") == kind
            and _mapping(resource.get("metadata"), f"{kind}/{name}.metadata").get("name") == name
        )
    except StopIteration as exc:
        raise DeploymentPolicyError(f"required resource is missing: {kind}/{name}") from exc


def _pod_template(workload: dict[str, Any]) -> dict[str, Any]:
    kind = cast(str, workload["kind"])
    name = cast(str, _mapping(workload["metadata"], "metadata")["name"])
    spec = _mapping(workload.get("spec"), f"{kind}/{name}.spec")
    if kind == "CronJob":
        job_template = _mapping(spec.get("jobTemplate"), f"{kind}/{name}.jobTemplate")
        job_spec = _mapping(job_template.get("spec"), f"{kind}/{name}.jobTemplate.spec")
        return _mapping(job_spec.get("template"), f"{kind}/{name}.template")
    return _mapping(spec.get("template"), f"{kind}/{name}.template")


def _validate_container(
    container: dict[str, Any],
    *,
    workload_name: str,
    expected_image_digest: str,
    release: dict[str, str],
    configuration_resource: str,
) -> str:
    name = container.get("name")
    image = container.get("image")
    if not isinstance(name, str) or not name:
        raise DeploymentPolicyError(f"{workload_name} has an unnamed container")
    if not isinstance(image, str) or not image.endswith(f"@{expected_image_digest}"):
        raise DeploymentPolicyError(
            f"{workload_name}/{name} must use the approved digest {expected_image_digest}"
        )
    if image.endswith(f"@{PLACEHOLDER_DIGEST}") or ":latest" in image:
        raise DeploymentPolicyError(
            f"{workload_name}/{name} uses a non-deployable image placeholder"
        )

    security = _mapping(container.get("securityContext"), f"{workload_name}/{name}.securityContext")
    if security.get("privileged") is True:
        raise DeploymentPolicyError(f"{workload_name}/{name} cannot be privileged")
    if security.get("allowPrivilegeEscalation") is not False:
        raise DeploymentPolicyError(f"{workload_name}/{name} allows privilege escalation")
    if security.get("readOnlyRootFilesystem") is not True:
        raise DeploymentPolicyError(f"{workload_name}/{name} requires a read-only root filesystem")
    container_uid = security.get("runAsUser")
    container_gid = security.get("runAsGroup")
    if (
        security.get("runAsNonRoot") is False
        or container_uid is not None
        and (
            not isinstance(container_uid, int)
            or isinstance(container_uid, bool)
            or container_uid <= 0
        )
        or container_gid is not None
        and (
            not isinstance(container_gid, int)
            or isinstance(container_gid, bool)
            or container_gid <= 0
        )
    ):
        raise DeploymentPolicyError(f"{workload_name}/{name} cannot override non-root execution")
    container_seccomp = security.get("seccompProfile")
    if (
        container_seccomp is not None
        and _mapping(container_seccomp, f"{workload_name}/{name}.seccompProfile").get("type")
        != "RuntimeDefault"
    ):
        raise DeploymentPolicyError(
            f"{workload_name}/{name} cannot override RuntimeDefault seccomp"
        )
    capabilities = _mapping(security.get("capabilities"), f"{workload_name}/{name}.capabilities")
    if set(_sequence(capabilities.get("drop"), f"{workload_name}/{name}.capabilities.drop")) != {
        "ALL"
    }:
        raise DeploymentPolicyError(f"{workload_name}/{name} must drop all Linux capabilities")

    resources = _mapping(container.get("resources"), f"{workload_name}/{name}.resources")
    for boundary in ("requests", "limits"):
        values = _mapping(resources.get(boundary), f"{workload_name}/{name}.resources.{boundary}")
        if not REQUIRED_RESOURCE_KEYS.issubset(values) or any(
            not str(values[key]).strip() for key in REQUIRED_RESOURCE_KEYS
        ):
            raise DeploymentPolicyError(
                f"{workload_name}/{name} requires cpu, memory and ephemeral-storage {boundary}"
            )

    env_from = _sequence(container.get("envFrom"), f"{workload_name}/{name}.envFrom")
    secret_names = {
        _mapping(_mapping(item, "envFrom item").get("secretRef"), "secretRef").get("name")
        for item in env_from
        if isinstance(item, dict) and "secretRef" in item
    }
    if secret_names != {configuration_resource}:
        raise DeploymentPolicyError(
            f"{workload_name}/{name} must load only the external {configuration_resource} Secret"
        )
    environment = _sequence(container.get("env"), f"{workload_name}/{name}.env")
    observed_environment: dict[str, object] = {}
    for item_value in environment:
        item = _mapping(item_value, f"{workload_name}/{name}.env item")
        variable = item.get("name")
        if not isinstance(variable, str) or variable in observed_environment:
            raise DeploymentPolicyError(
                f"{workload_name}/{name} contains an unnamed or duplicate environment variable"
            )
        observed_environment[variable] = item.get("value")
    for field, variable in RELEASE_ENV.items():
        if observed_environment.get(variable) != release[field]:
            raise DeploymentPolicyError(
                f"{workload_name}/{name} must bind {variable} to the approved release"
            )
    return image


def _validate_release_annotations(
    metadata: dict[str, Any],
    *,
    field: str,
    release: dict[str, str],
) -> None:
    annotations = _mapping(metadata.get("annotations"), f"{field}.annotations")
    for release_field, annotation in RELEASE_ANNOTATIONS.items():
        if annotations.get(annotation) != release[release_field]:
            raise DeploymentPolicyError(f"{field} must bind {annotation} to the approved release")


def _validate_workload(
    workload: dict[str, Any],
    expected_image_digest: str,
    release: dict[str, str],
) -> dict[str, Any]:
    kind = cast(str, workload["kind"])
    metadata = _mapping(workload["metadata"], f"{kind}.metadata")
    name = cast(str, metadata["name"])
    template = _pod_template(workload)
    _validate_release_annotations(
        metadata,
        field=f"{kind}/{name}.metadata",
        release=release,
    )
    _validate_release_annotations(
        _mapping(template.get("metadata"), f"{kind}/{name}.template.metadata"),
        field=f"{kind}/{name}.template.metadata",
        release=release,
    )
    pod_spec = _mapping(template.get("spec"), f"{kind}/{name}.podSpec")
    service_account = CARE_SERVICE_ACCOUNT if name == CARE_WORKLOAD else RUNTIME_SERVICE_ACCOUNT
    configuration_resource = (
        CARE_CONFIGURATION_RESOURCE if name == CARE_WORKLOAD else RUNTIME_CONFIGURATION_RESOURCE
    )
    if pod_spec.get("serviceAccountName") != service_account:
        raise DeploymentPolicyError(f"{kind}/{name} must use {service_account}")
    if pod_spec.get("automountServiceAccountToken") is not False:
        raise DeploymentPolicyError(f"{kind}/{name} must disable service-account token mounting")
    for forbidden in ("hostNetwork", "hostPID", "hostIPC"):
        if pod_spec.get(forbidden) is True:
            raise DeploymentPolicyError(f"{kind}/{name} cannot enable {forbidden}")

    pod_security = _mapping(pod_spec.get("securityContext"), f"{kind}/{name}.securityContext")
    if pod_security.get("runAsNonRoot") is not True:
        raise DeploymentPolicyError(f"{kind}/{name} must run as non-root")
    for field in ("runAsUser", "runAsGroup"):
        value = pod_security.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise DeploymentPolicyError(f"{kind}/{name}.{field} must be a positive numeric ID")
    seccomp = _mapping(pod_security.get("seccompProfile"), f"{kind}/{name}.seccompProfile")
    if seccomp.get("type") != "RuntimeDefault":
        raise DeploymentPolicyError(f"{kind}/{name} must use RuntimeDefault seccomp")

    volumes = _sequence(pod_spec.get("volumes", []), f"{kind}/{name}.volumes")
    if any("hostPath" in _mapping(volume, f"{kind}/{name}.volume") for volume in volumes):
        raise DeploymentPolicyError(f"{kind}/{name} cannot mount hostPath volumes")
    containers = _sequence(pod_spec.get("containers"), f"{kind}/{name}.containers")
    if not containers:
        raise DeploymentPolicyError(f"{kind}/{name} must contain at least one container")
    images = [
        _validate_container(
            _mapping(container, f"{kind}/{name}.container"),
            workload_name=f"{kind}/{name}",
            expected_image_digest=expected_image_digest,
            release=release,
            configuration_resource=configuration_resource,
        )
        for container in containers
    ]
    if pod_spec.get("initContainers"):
        for container in _sequence(pod_spec["initContainers"], f"{kind}/{name}.initContainers"):
            images.append(
                _validate_container(
                    _mapping(container, f"{kind}/{name}.initContainer"),
                    workload_name=f"{kind}/{name}",
                    expected_image_digest=expected_image_digest,
                    release=release,
                    configuration_resource=configuration_resource,
                )
            )
    return {"kind": kind, "name": name, "images": images}


def _validate_availability(documents: list[dict[str, Any]]) -> None:
    api = _named(documents, "Deployment", "windops-api")
    api_spec = _mapping(api.get("spec"), "Deployment/windops-api.spec")
    if not isinstance(api_spec.get("replicas"), int) or api_spec["replicas"] < 3:
        raise DeploymentPolicyError("windops-api requires at least three replicas")
    strategy = _mapping(api_spec.get("strategy"), "Deployment/windops-api.strategy")
    rolling = _mapping(strategy.get("rollingUpdate"), "Deployment/windops-api.rollingUpdate")
    if strategy.get("type") != "RollingUpdate" or rolling.get("maxUnavailable") != 0:
        raise DeploymentPolicyError("windops-api rollout must preserve full availability")

    api_container = _mapping(
        _sequence(
            _mapping(_pod_template(api).get("spec"), "windops-api.podSpec").get("containers"),
            "windops-api.containers",
        )[0],
        "windops-api.container",
    )
    expected_probes = {
        "startupProbe": "/api/v1/healthz",
        "livenessProbe": "/api/v1/healthz",
        "readinessProbe": "/api/v1/readyz",
    }
    for probe_name, path in expected_probes.items():
        probe = _mapping(api_container.get(probe_name), f"windops-api.{probe_name}")
        http_get = _mapping(probe.get("httpGet"), f"windops-api.{probe_name}.httpGet")
        if http_get.get("path") != path:
            raise DeploymentPolicyError(f"windops-api.{probe_name} must probe {path}")

    pdb = _mapping(
        _named(documents, "PodDisruptionBudget", "windops-api").get("spec"),
        "PodDisruptionBudget/windops-api.spec",
    )
    if not isinstance(pdb.get("minAvailable"), int) or pdb["minAvailable"] < 2:
        raise DeploymentPolicyError("windops-api PDB requires at least two available replicas")
    hpa = _mapping(
        _named(documents, "HorizontalPodAutoscaler", "windops-api").get("spec"),
        "HorizontalPodAutoscaler/windops-api.spec",
    )
    min_replicas = hpa.get("minReplicas")
    max_replicas = hpa.get("maxReplicas")
    if (
        not isinstance(min_replicas, int)
        or isinstance(min_replicas, bool)
        or min_replicas < 3
        or not isinstance(max_replicas, int)
        or isinstance(max_replicas, bool)
        or max_replicas < 6
    ):
        raise DeploymentPolicyError("windops-api HPA bounds are below the production minimum")


def _validate_network_peer(value: object, field: str) -> None:
    peer = _mapping(value, field)
    selectors = [key for key in ("namespaceSelector", "podSelector") if key in peer]
    if "ipBlock" not in peer and not selectors:
        raise DeploymentPolicyError(f"{field} must constrain a namespace, pod or CIDR")
    for selector_name in selectors:
        selector = _mapping(peer[selector_name], f"{field}.{selector_name}")
        match_labels = selector.get("matchLabels")
        if not isinstance(match_labels, dict) or not match_labels:
            raise DeploymentPolicyError(f"{field}.{selector_name} cannot select every target")
    if "ipBlock" in peer:
        block = _mapping(peer["ipBlock"], f"{field}.ipBlock")
        cidr = block.get("cidr")
        if not isinstance(cidr, str):
            raise DeploymentPolicyError(f"{field}.ipBlock.cidr must be a valid CIDR")
        try:
            network = ipaddress.ip_network(cidr, strict=True)
        except ValueError as exc:
            raise DeploymentPolicyError(f"{field}.ipBlock.cidr must be a valid CIDR") from exc
        minimum_prefix = 8 if network.version == 4 else 32
        if network.prefixlen < minimum_prefix:
            raise DeploymentPolicyError(f"{field}.ipBlock is too broad for production egress")


def _validate_network_rules(value: object, field: str, peer_key: str) -> None:
    rules = _sequence(value, field)
    if not rules:
        raise DeploymentPolicyError(f"{field} requires at least one rule")
    for rule_index, rule_value in enumerate(rules):
        rule = _mapping(rule_value, f"{field}[{rule_index}]")
        peer_values = rule.get(peer_key)
        if peer_values is None:
            raise DeploymentPolicyError(f"{field} requires explicit destinations or sources")
        peers = _sequence(peer_values, f"{field}[{rule_index}].{peer_key}")
        if not peers:
            raise DeploymentPolicyError(f"{field} requires explicit destinations or sources")
        for peer_index, peer in enumerate(peers):
            _validate_network_peer(peer, f"{field}[{rule_index}].{peer_key}[{peer_index}]")
        ports = _sequence(rule.get("ports"), f"{field}[{rule_index}].ports")
        if not ports:
            raise DeploymentPolicyError(f"{field} requires explicit ports")
        for port_index, port_value in enumerate(ports):
            port = _mapping(port_value, f"{field}[{rule_index}].ports[{port_index}]")
            protocol = port.get("protocol", "TCP")
            number = port.get("port")
            if protocol not in {"TCP", "UDP", "SCTP"}:
                raise DeploymentPolicyError(f"{field} contains an unsupported protocol")
            if "endPort" in port:
                raise DeploymentPolicyError(f"{field} cannot use port ranges")
            if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= 65535:
                raise DeploymentPolicyError(f"{field} requires numeric ports from 1 to 65535")


def _validate_network_policy(documents: list[dict[str, Any]]) -> None:
    default_deny = _mapping(
        _named(documents, "NetworkPolicy", "windops-default-deny").get("spec"),
        "NetworkPolicy/windops-default-deny.spec",
    )
    if (
        default_deny.get("podSelector") != {}
        or set(default_deny.get("policyTypes", [])) != {"Ingress", "Egress"}
        or default_deny.get("ingress") not in (None, [])
        or default_deny.get("egress") not in (None, [])
    ):
        raise DeploymentPolicyError("windops-default-deny must deny all ingress and egress")

    ingress = _mapping(
        _named(documents, "NetworkPolicy", "windops-api-ingress").get("spec"),
        "NetworkPolicy/windops-api-ingress.spec",
    )
    if ingress.get("podSelector") != {
        "matchLabels": {"app.kubernetes.io/name": "windops-api"}
    } or ingress.get("policyTypes") != ["Ingress"]:
        raise DeploymentPolicyError("windops-api-ingress must select only API pods")
    _validate_network_rules(ingress.get("ingress"), "windops-api-ingress.ingress", "from")

    egress = _mapping(
        _named(documents, "NetworkPolicy", "windops-runtime-egress").get("spec"),
        "NetworkPolicy/windops-runtime-egress.spec",
    )
    if egress.get("podSelector") != {
        "matchExpressions": [
            {
                "key": "app.kubernetes.io/component",
                "operator": "NotIn",
                "values": ["care-worker"],
            }
        ]
    } or egress.get("policyTypes") != ["Egress"]:
        raise DeploymentPolicyError("windops-runtime-egress must exclude CARE worker pods")
    _validate_network_rules(egress.get("egress"), "windops-runtime-egress.egress", "to")

    care_egress = _mapping(
        _named(documents, "NetworkPolicy", "windops-care-egress").get("spec"),
        "NetworkPolicy/windops-care-egress.spec",
    )
    if care_egress.get("podSelector") != {
        "matchLabels": {"app.kubernetes.io/component": "care-worker"}
    } or care_egress.get("policyTypes") != ["Egress"]:
        raise DeploymentPolicyError("windops-care-egress must select only CARE worker pods")
    _validate_network_rules(care_egress.get("egress"), "windops-care-egress.egress", "to")
    care_ports = {
        port["port"]
        for rule in _sequence(care_egress.get("egress"), "windops-care-egress.egress")
        for port in _sequence(_mapping(rule, "care egress rule").get("ports"), "care ports")
    }
    if care_ports != {53, 5432, 9000}:
        raise DeploymentPolicyError("windops-care-egress may use only DNS, PostgreSQL and MinIO")


def _validate_care_workload(documents: list[dict[str, Any]]) -> None:
    workload = _named(documents, "CronJob", CARE_WORKLOAD)
    spec = _mapping(workload.get("spec"), f"CronJob/{CARE_WORKLOAD}.spec")
    if (
        spec.get("suspend") is not True
        or spec.get("concurrencyPolicy") != "Forbid"
        or spec.get("timeZone") != "Etc/UTC"
    ):
        raise DeploymentPolicyError("CARE workload must be suspended, serialized and UTC-bound")
    job_spec = _mapping(
        _mapping(spec.get("jobTemplate"), "CARE jobTemplate").get("spec"),
        "CARE job spec",
    )
    expected_job_limits = {
        "parallelism": 1,
        "completions": 1,
        "backoffLimit": 2,
        "activeDeadlineSeconds": 72000,
    }
    if any(job_spec.get(field) != value for field, value in expected_job_limits.items()):
        raise DeploymentPolicyError("CARE workload retry, concurrency or timeout limits drifted")
    pod_spec = _mapping(_pod_template(workload).get("spec"), "CARE pod spec")
    if pod_spec.get("restartPolicy") != "Never":
        raise DeploymentPolicyError("CARE workload must use job-level bounded retries")
    container = _mapping(
        _sequence(pod_spec.get("containers"), "CARE containers")[0],
        "CARE container",
    )
    environment = {
        item["name"]: item.get("value")
        for item in _sequence(container.get("env"), "CARE environment")
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    required_environment = {
        "WINDOPS_CARE_QUEUE": "care-v6-offline",
        "WINDOPS_CARE_MAX_CONCURRENCY": "1",
        "WINDOPS_CARE_MAX_ATTEMPTS": "3",
    }
    if any(environment.get(name) != value for name, value in required_environment.items()):
        raise DeploymentPolicyError("CARE queue, concurrency or attempt contract drifted")
    script = "\n".join(str(value) for value in container.get("args", []))
    required_tokens = {
        "windops-care-dependency-closure",
        "windops-care-full-scale import",
        "windops-care-full-scale evaluate",
        "windops-care-full-scale register",
        "--use-care-worker-runtime",
        "--state-path /care/work/state/import.json",
        "--state-path /care/work/state/evaluate.json",
    }
    if container.get("command") != ["/bin/sh", "-ec"] or any(
        token not in script for token in required_tokens
    ):
        raise DeploymentPolicyError("CARE workload does not execute the governed full-scale flow")
    mounts = {
        mount.get("name"): mount
        for mount in _sequence(container.get("volumeMounts"), "CARE volume mounts")
        if isinstance(mount, dict)
    }
    if mounts.get("care-source", {}).get("readOnly") is not True:
        raise DeploymentPolicyError("CARE source volume must be mounted read-only")
    volumes = {
        volume.get("name"): volume
        for volume in _sequence(pod_spec.get("volumes"), "CARE volumes")
        if isinstance(volume, dict)
    }
    source_claim = _mapping(
        volumes.get("care-source", {}).get("persistentVolumeClaim"),
        "CARE source claim",
    )
    if source_claim != {"claimName": "windops-care-source", "readOnly": True}:
        raise DeploymentPolicyError("CARE source PVC binding must be read-only")
    workspace_claim = _mapping(
        volumes.get("care-workspace", {}).get("persistentVolumeClaim"),
        "CARE workspace claim",
    )
    if workspace_claim != {"claimName": "windops-care-workspace"}:
        raise DeploymentPolicyError("CARE workspace must use its isolated PVC")
    expected_storage = {
        "windops-care-source": "windops-encrypted-care-source",
        "windops-care-workspace": "windops-encrypted-care-workspace",
    }
    for claim_name, storage_class in expected_storage.items():
        claim = _mapping(
            _named(documents, "PersistentVolumeClaim", claim_name).get("spec"),
            f"PersistentVolumeClaim/{claim_name}.spec",
        )
        if claim.get("storageClassName") != storage_class:
            raise DeploymentPolicyError(f"{claim_name} must use approved encrypted storage")


def verify_deployment_policy(
    manifests: Path,
    *,
    expected_image_digest: str,
    expected_release_id: str,
    expected_commit_sha: str,
    approved_backup_storage_class: str,
) -> dict[str, Any]:
    if (
        re.fullmatch(r"sha256:[0-9a-f]{64}", expected_image_digest) is None
        or expected_image_digest == PLACEHOLDER_DIGEST
    ):
        raise DeploymentPolicyError(
            "expected image digest must be a non-placeholder SHA-256 digest"
        )
    if (
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,127}", expected_release_id) is None
        or expected_release_id.lower() in {"development", "unknown", "unreleased"}
        or "replace" in expected_release_id.lower()
    ):
        raise DeploymentPolicyError("expected release ID must be immutable and non-placeholder")
    if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", expected_commit_sha) is None:
        raise DeploymentPolicyError("expected commit SHA must be a full lowercase Git SHA")
    if re.fullmatch(
        r"[a-z0-9](?:[-a-z0-9.]{0,251}[a-z0-9])?",
        approved_backup_storage_class,
    ) is None or approved_backup_storage_class.lower() in {
        "default",
        "local-path",
        "standard",
    }:
        raise DeploymentPolicyError(
            "an explicitly approved encrypted backup storage class is required"
        )

    documents, files = _documents(manifests)
    observed_identities = {
        (cast(str, resource["kind"]), cast(str, _mapping(resource["metadata"], "metadata")["name"]))
        for resource in documents
    }
    missing = REQUIRED_RESOURCE_IDENTITIES - observed_identities
    if missing:
        formatted = ", ".join(f"{kind}/{name}" for kind, name in sorted(missing))
        raise DeploymentPolicyError(f"required rendered resources are missing: {formatted}")
    if any(resource.get("kind") == "Secret" for resource in documents):
        raise DeploymentPolicyError("rendered manifests cannot contain Secret resources")

    namespace = _mapping(
        _named(documents, "Namespace", EXPECTED_NAMESPACE).get("metadata"),
        "Namespace/windops.metadata",
    )
    namespace_labels = _mapping(namespace.get("labels"), "Namespace/windops.labels")
    for mode in ("enforce", "audit", "warn"):
        if namespace_labels.get(f"pod-security.kubernetes.io/{mode}") != "restricted":
            raise DeploymentPolicyError(f"windops namespace Pod Security {mode} must be restricted")

    for account_name in (RUNTIME_SERVICE_ACCOUNT, CARE_SERVICE_ACCOUNT):
        service_account = _named(documents, "ServiceAccount", account_name)
        if service_account.get("automountServiceAccountToken") is not False:
            raise DeploymentPolicyError(
                f"{account_name} ServiceAccount must disable token automount"
            )

    pvc = _mapping(
        _named(documents, "PersistentVolumeClaim", "windops-backups").get("spec"),
        "PersistentVolumeClaim/windops-backups.spec",
    )
    if pvc.get("storageClassName") != approved_backup_storage_class:
        raise DeploymentPolicyError("backup PVC does not use the approved encrypted storage class")

    release = {
        "release_id": expected_release_id,
        "commit_sha": expected_commit_sha,
        "image_digest": expected_image_digest,
    }
    workloads = [
        _validate_workload(resource, expected_image_digest, release)
        for resource in documents
        if resource.get("kind") in WORKLOAD_KINDS
    ]
    _validate_availability(documents)
    _validate_care_workload(documents)
    _validate_network_policy(documents)
    return {
        "format_version": 1,
        "gate": "deployment_policy",
        "status": "passed",
        "checked_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "expected_image_digest": expected_image_digest,
        "expected_release_id": expected_release_id,
        "expected_commit_sha": expected_commit_sha,
        "approved_backup_storage_class": approved_backup_storage_class,
        "manifest_files": files,
        "resource_count": len(documents),
        "workloads": workloads,
        "checks": [
            "rendered_namespace",
            "required_resources",
            "immutable_images",
            "restricted_pod_security",
            "external_secret_reference",
            "resource_boundaries",
            "availability_and_probes",
            "destination_scoped_network_policy",
            "encrypted_backup_storage",
            "isolated_care_execution_plane",
            "care_checkpoint_retry_idempotency",
            "care_scoped_storage_credentials",
        ],
    }


def _write_report(path: Path, report: dict[str, Any]) -> None:
    write_atomic_json(
        path,
        report,
        symlink_error=DeploymentPolicyError(
            "deployment-policy report cannot overwrite a symbolic link"
        ),
        temporary_suffix=".tmp",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify rendered OpenVigil Kubernetes manifests and emit release evidence"
    )
    parser.add_argument("--manifests", type=Path, required=True)
    parser.add_argument("--expected-image-digest", required=True)
    parser.add_argument("--expected-release-id", required=True)
    parser.add_argument("--expected-commit-sha", required=True)
    parser.add_argument("--approved-backup-storage-class", required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = verify_deployment_policy(
            args.manifests,
            expected_image_digest=args.expected_image_digest,
            expected_release_id=args.expected_release_id,
            expected_commit_sha=args.expected_commit_sha,
            approved_backup_storage_class=args.approved_backup_storage_class,
        )
        if args.report:
            _write_report(args.report, report)
    except (DeploymentPolicyError, OSError) as exc:
        print(
            json.dumps(
                {"gate": "deployment_policy", "status": "failed", "error": str(exc)},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
