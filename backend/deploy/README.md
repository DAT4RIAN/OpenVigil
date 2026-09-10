# WindOps production deployment baseline

This directory is a vendor-neutral Kubernetes baseline for the FastAPI API,
Dramatiq workers, durable outbox relay, one-time Alembic migration, disruption
budget, autoscaling, default-deny network policy, and scheduled verified backup.
It does not deploy PostgreSQL, Redis, MinIO, Neo4j, LiteLLM, the model serving
platform, ingress, TLS certificates, or a secret manager; those must be managed
production services.

## Release image

Build `backend/Dockerfile` from the backend directory. The default Python base
digest is deliberately all zeroes and cannot build. Supply an approved,
vulnerability-scanned `python:3.12.11-slim-trixie@sha256:<digest>` through the
`PYTHON_BASE_IMAGE` build argument. Runtime dependencies come from the
hash-locked `requirements.container.txt`, generated from `uv.lock`; regenerate
and review it whenever the lock changes. The image runs as UID/GID 10001 and
includes no test or development dependencies. `pg_dump`, `pg_restore`, and
`psql` are copied from the exact digest-bound PostgreSQL 16 TimescaleDB image
and must match the production server major; a merely newer client is rejected
because it can emit settings unknown to the older restore target. The exact
reviewed Python and PostgreSQL client images are recorded in
`deploy/release-policy.json`. Before any cluster apply:

1. scan the image and close all critical/high findings;
2. generate and retain an SPDX or CycloneDX SBOM;
3. sign the image and verify the signature in the target admission policy;
4. replace every `registry.invalid/...@sha256:000...` reference with the exact
   approved image digest; mutable tags are not an accepted release input.

The base-image and release-image placeholders intentionally cannot build or
deploy a working service.

## Runtime configuration

Provision a namespaced Secret named `windops-runtime` through the approved
secret manager/CSI operator. It must contain the complete `WINDOPS_*`
production configuration described in `example.env`. Do not create the Secret
from a checked-in `.env` file. In particular, production validation requires
TLS service URLs, all five MinIO buckets, Sites delegation and role mappings,
telemetry source policies and distinct credentials, LiteLLM/embedding/model
targets, trusted external Host names, Redis rate limiting, OTLP and a dedicated
metrics token. The same immutable release ID, full Git commit SHA and approved
image digest must be configured in the backend and recorded in the release
evidence manifest.

### CARE benchmark object storage

Provision `WINDOPS_MINIO_CARE_BUCKET` as a private, versioned bucket separate
from production field evidence. Keep the five configured prefixes under
`care/v6/`: `raw`, `standard`, `quality`, `predictions`, and `reports`. Apply
`care-minio-lifecycle.json` to the bucket. The checked-in
`care-minio-worker-policy.json` is the least-privilege policy template for the
dedicated benchmark worker; if the bucket name is overridden, render that
resource ARN to the exact configured bucket before applying it. Do not attach
the policy to browser or general frontend identities.

`care-minio-cleanup-policy.json` is a separate, normally unattached break-glass
policy for the governed cleanup worker. It cannot list, read, or delete the
`raw` layer. Before temporarily assuming it, the worker must validate the
dataset content hash, an exact farm/event or model/run scope, the bounded object
list and every object SHA-256 with `CareArtifactCleanupScope`; execution requires
the resulting scope hash as a second confirmation and writes a durable
`benchmark_cleanup` audit event. Never grant this policy to the import worker,
API, browser, or a production asset service account.

The standard backup job includes the CARE bucket. Production backup storage
and recovery drills must therefore have independent read access to that bucket,
while the benchmark worker does not receive backup-administration permission.

Set `WINDOPS_BIND_HOST=0.0.0.0` and include both the external ingress host and
`windops-api.windops.svc` in `WINDOPS_TRUSTED_HOSTS`. Kubernetes probes send the
internal DNS Host explicitly; loopback/default test hosts are rejected by
production configuration validation.

Label only the namespace containing the approved private ingress or Sites
backend gateway with:

```text
windops.openai.com/gateway-access=true
```

All runtime dependency traffic must pass through approved in-cluster services
or egress gateways. Label both their namespace and destination pods with:

```text
windops.openai.com/runtime-dependency-access=true
```

The egress policy allows only kube-dns plus those explicitly labelled targets
on the standard TLS, OTLP, PostgreSQL, Redis, Neo4j and MinIO ports. If a
managed dependency uses another port or an environment-specific CNI/FQDN
policy, add a reviewed overlay; never remove the destination selector or
disable default deny.

The backup PVC names `windops-encrypted-backup` as a fail-closed baseline.
Map that name to an approved StorageClass providing encryption at rest,
snapshots and remote replication, or replace it in a reviewed environment
overlay and pass the exact rendered name to the policy verifier.

## Ordered rollout

Render the kustomization and run policy validation before changing the cluster.
Use a release-specific migration Job name so its immutable execution record is
retained. The required order is:

```text
windops-deployment-policy \
  --manifests <rendered-manifest.yaml> \
  --expected-image-digest sha256:<approved-release-digest> \
  --expected-release-id <approved-release-id> \
  --expected-commit-sha <full-git-commit-sha> \
  --approved-backup-storage-class <approved-encrypted-class> \
  --report <release-evidence-directory>/deployment-policy.json
```

The input must be the final rendered manifest, after namespace, exact image
digest, storage class and environment overlays are applied. The verifier
rejects embedded Secrets, mutable/foreign images, root or privileged pods,
missing resource boundaries/probes, broad egress, missing availability policy
and unapproved backup storage. It also requires every API, worker, relay,
migration and backup pod to carry the same release ID, commit and digest in
server-owned annotations and runtime variables. Its JSON output is the `deployment_policy`
release-gate report; Kubernetes API schema/admission validation must still be
retained separately in the same report or its referenced evidence.

The required rollout order is:

1. verified backup and approved change window;
2. `windops-runtime` secret revision and exact image digest;
3. migration Job completion at Alembic head `0026_schema_contract_alignment`;
4. API, worker and relay rollout with all probes healthy;
5. external release test with no skip;
6. Sites configuration/publish and post-deploy verification;
7. DAST, SLO alert exercise and evidence retention.

The protected GitHub `release-candidate` workflow performs the build, registry
push, GitHub provenance attestation, keyless signing, Trivy blocking scan, SPDX
SBOM attestation, image structure/entrypoint/lock verification, hardened
migration and health/readiness smoke, exact-digest manifest render, non-skipped
isolated dependency acceptance and verified backup subset. It uploads the
commit-to-image-to-manifest-to-environment chain as a retained artifact. Missing
protected configuration, prior CI checks, scan/signature evidence or any skipped
external test fails the workflow; repository placeholders are never release
inputs.

Collect every report under one evidence directory and create
`release-evidence.json` plus `release-evidence.sha256` according to
`windops_backend.operations.release_gate.RELEASE_EVIDENCE_SCHEMA`. The final
go/no-go check is:

```text
windops-release-gate --evidence-dir <release-evidence-directory>
```

It fails if any of the image scan, SBOM, signature, rendered deployment policy,
migration, real dependency, DR drill, DAST, accessibility/visual, SLO or Sites
post-deploy gates is absent. Every gate report must use `GATE_REPORT_SCHEMA`, bind
to the exact release identity, cover all gate-specific `REQUIRED_GATE_CHECKS`, and
reference non-empty SHA-256-addressed raw artifacts under the same evidence
directory. The verifier also rejects duplicate gates/checks/artifacts, undeclared
references, path traversal, symlinks, empty/tampered evidence and the non-deployable
image digest placeholder. Direct tool output such as `deployment-policy.json` is a
raw artifact; wrap it in the standardized gate summary instead of listing it as
the manifest report itself.

Before Sites promotion, configure `WINDOPS_BACKEND_EXPECTED_RELEASE_ID` and
`WINDOPS_BACKEND_EXPECTED_IMAGE_DIGEST` to the values exposed by the approved
backend deployment. The Worker verifies `/readyz` and every proxied response;
missing or mismatched release identity fails closed with HTTP 503.

The API has three baseline replicas, zero-unavailable rolling updates, a
two-replica disruption budget, and CPU/memory autoscaling. The relay remains a
single logical scanner because durable claims fence duplicate event delivery;
Dramatiq workers scale independently.

The backup CronJob writes signed, content-addressed bundles to a 100 GiB PVC.
The selected StorageClass must provide encryption at rest and snapshot/remote
replication. PVC history alone is not an off-site backup. Quarterly recovery
still requires `windops-dr-drill` against an isolated database and disjoint
MinIO buckets.
