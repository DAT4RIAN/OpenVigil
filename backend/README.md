# OpenVigil Python backend — durable Mission and work-order platform

This Python 3.12 service implements the audited operational chain:

```text
SCADA/manual alarm → idempotent Mission command → durable outbox
→ parameterized LangGraph analysis → human review → approval-gated work order
→ governed ordered field tasks → measured health gate → resolved alarm → knowledge case
```

## Runtime boundary

Production requires PostgreSQL/asyncpg with TimescaleDB and pgvector, Redis with
Dramatiq, MinIO, Neo4j, and LiteLLM. Production configuration rejects SQLite, runtime
schema bootstrap, demo seed, deterministic reasoning, non-TLS database/Redis/
MinIO/Neo4j connections, example secrets, and inline outbox draining. SQLite,
the in-memory artifact verifier, and the in-memory graph store are explicitly test-only.

SCADA persistence never waits for LangGraph or LiteLLM. The API commits the
sample, alarm, mission, and `outbox_events` row atomically, then dispatches the
event to Dramatiq. A worker claims it with a five-minute recoverable lease. An
early redelivery is retried rather than acknowledged; stale processing leases
can be reclaimed. Every claim receives a new fencing token; success/failure
updates require the current token, and the handler rechecks ownership before
commit, so an expired worker cannot overwrite a newer lease or commit stale
graph changes. If analysis fails, that transaction rolls back while the failed
node's public input/tool/error context and failed outbox status are committed
independently.

## Authentication

Every business read and write requires `Authorization: Bearer <role-secret>`;
only `/healthz` and `/readyz` remain unauthenticated operational probes. Each
secret maps server-side to one concrete service subject and role. Unsigned
subject headers are ignored. Before business data is read, production appends a
minimized attribution event to a bounded durable Redis stream; raw query values
and full scope lists are represented only by SHA-256 fingerprints and counts.
`windops-read-audit-worker` commits up to 500 events per transaction into monthly
`read_access_audits` partitions, acknowledges only after commit, and reclaims
unacknowledged deliveries. Redis failure or backlog saturation fails the read
closed with `READ_AUDIT_UNAVAILABLE` or `READ_AUDIT_BACKPRESSURE`; a PostgreSQL
audit outage leaves events queued and does not block reads until that explicit
capacity boundary. The test-only explicit bypass is rejected outside
`WINDOPS_ENVIRONMENT=test`.
Actor names in JSON are ignored; approval and field evidence identity comes
from the authenticated principal.

Delegated write JWTs are single-use: PostgreSQL atomically consumes the hashed
`jti` before a `POST`, `PUT`, `PATCH`, or `DELETE`, and replay-store failure
fails closed. Read tokens remain replayable within their short validity window.
Every retryable side-effect `POST` except source-event-idempotent SCADA ingest
requires `Idempotency-Key`; receipts are scoped by authenticated subject,
command type, target, key, and canonical request hash. See
`../docs/runbooks/delegated-replay-and-command-idempotency.md` for response,
audit, cleanup, and incident contracts.

Knowledge-graph reads also require an explicit backend-owned scope grant in
`WINDOPS_IDENTITY_SCOPE_MAPPINGS`. A grant can constrain `tenant_ids`,
`wind_farm_ids`, `turbine_ids`, `entity_ids` and `data_scopes`; `allow_global`
must be enabled separately for tenant-neutral manuals and failure-mode nodes.
The signed Sites subject is used only to select this mapping. Query parameters
cannot widen it, and a production subject without a mapping receives
`GRAPH_SCOPE_REQUIRED`.

| Operation           | Required role          |
| ------------------- | ---------------------- |
| SCADA ingest        | `scada_ingestor`       |
| approve / reject    | `operations_approver`  |
| request revision    | `maintenance_reviewer` |
| escalate            | `operations_manager`   |
| create Mission      | `operations_manager`   |
| complete field task | `field_technician`     |

Production loads no reference data automatically. Development and test
startup auto-load the versioned Agent/Skill/Tool catalog (and the WT-023 demo
master data when `WINDOPS_DEMO_SEED=true`, which production configuration
rejects); production startup loads neither. After applying Alembic, an
operations manager explicitly imports both the catalog and the controlled
master-data pack (farm, WT-023, knowledge document, resources, weather window):

```powershell
windops-reference-import --reference-pack wt023
```

The command securely prompts for the operations-manager API key. It creates no
alarm, mission, decision, approval, work order, or agent execution. The
controlled manual body lives in
PostgreSQL with a canonical `windops://knowledge/documents/{id}` citation;
provider embeddings are persisted there when vectorization runs. The importer
does not pretend to have uploaded a MinIO knowledge object.

`request_revision` records the review result, queues a new durable analysis,
reopens the Decision proposal and returns to a new revision-guarded review.
`escalate` keeps the Decision open and increments the revision, so a later
approve/reject/revise action remains valid. Neither result can be reused as the
approval that authorizes a work order.

## Field evidence gate

Tasks must complete in their governed sequence. A work-order plan contains 1–20
tasks, and every completion requires:

- `artifact_uri`
- `artifact_sha256` (64 hexadecimal characters)
- a non-empty structured `measurement`
- authenticated `verified_by` identity (server-owned)

Each task persists an extra-forbidden, versioned JSON Schema. The default
main-bearing plan remains a five-step controlled template:

| Task             | Required operational gate                                          |
| ---------------- | ------------------------------------------------------------------ |
| lubrication      | acceptable/clean condition and water content `≤500 ppm`            |
| vibration        | RMS `≤4.5 mm/s` and BPFO-band energy `≤10%`                        |
| temperature      | bearing temperature `≤75°C`                                        |
| borescope        | none/minor defect and spall area `≤5 mm²`                          |
| closure evidence | at least 3 photos, main-bearing health `≥78`, turbine health `≥82` |

Production accepts only `minio://bucket/object` artifacts. It checks object
existence off the async event loop and verifies either trusted SHA-256 metadata
or the streamed object content. Tests use an explicit in-memory verifier and
must pre-register each URI/hash. Health recovery and knowledge-case creation
are impossible until every governed task has exactly one verified,
schema-valid evidence record and the final task's measured health score meets
the plan's return-to-service threshold. Non-main-bearing Missions receive a
controlled three-step default, while an operations manager may supply a fully
validated plan with unique resource types, safety controls and a numeric
closure contract.

## Architecture and migrations

- FastAPI routes and Pydantic wire models
- SQLAlchemy async persistence and 11 domain tool adapters
- public LangGraph state only (no hidden chain-of-thought storage)
- LiteLLM schema-constrained production reasoning
- `AgentExecution`, Evidence, Decision, Approval and resource ledgers
- Neo4j derived knowledge graph with a PostgreSQL authoritative source
- idempotent graph projection events routed through the transactional outbox
- versioned Agent/Skill/Tool definitions and execution-to-version links
- `0001_wt023`: base domain, Timescale hypertable, pgvector index
- `0002_domain_audit`: structured evidence/decision/execution audit
- `0003_durable_execution`: transactional outbox and field-task evidence
- `0004_operational_hardening`: fencing leases, read attribution, catalog/version links
- `0005_generic_commands`: command idempotency receipts, governed work-order
  schemas/schedules, and typed resource/weather attributes
- `0006_decision_selection_traceability`: selected-alternative and approval traceability
- `0007_ordered_ingest_and_replayable_events`: ordered source ingestion, quarantine and events
- `0008_external_eam_work_orders`: durable EAM delivery and callback state
- `0009_knowledge_document_ingestion`: governed document objects, chunks and embeddings
- `0010_model_registry_and_predictions`: immutable model artifacts, deployments and predictions
- `0011_agent_tool_invocations`: governed Agent commands, releases and tool invocation ledger
- `0012_platform_governance`: data-source, contract and platform configuration revisions
- `0013_generated_reports`: immutable generated report snapshots
- `0014_reasoning_evaluations`: fail-closed reasoning evaluation records
- `0015_alarm_command_state`: revision-guarded acknowledgement and assignment state
- `0016_tenant_asset_access_scope`: tenant ownership on wind farms and graph-read scope boundary
- `0016_version_num_length`: widen Alembic's version table before longer revision IDs
- `0017_knowledge_document_access_scope`: trusted tenant, asset, and data-scope boundary on knowledge documents
- `0018_platform_configuration_security`: strict configuration schema metadata and secret-remediation audit evidence
- `0019_bounded_collection_indexes`: bounded operational pagination and latest-health query indexes
- `0020_delegated_replay_and_idempotency`: delegated-write nonce consumption and subject-scoped command receipts
- `0021_ingest_source_secret_audits`: strict Secret Manager validation and quarantine evidence for legacy ingest credentials
- `0022_diagnosis_priority_indexes`: selective alarm-severity and turbine-health indexes for bounded diagnosis priority pagination
- `0023_bounded_weather_selection`: composite farm/suitability/time index for deterministic bounded maintenance weather selection
- `0024_care_benchmark_metadata`: governed CARE dataset/event/evaluation/replay metadata, structured anomaly prediction provenance, and dual alarm-source constraints
- `0025_benchmark_event_score_scope`: keep point-scorable CARE events valid when a single-class fold has no run-aggregate CARE score
- `0026_schema_contract_alignment`: backfill and require ORM-mandatory timestamps while aligning PostgreSQL indexes and constraints with the declared model contract
- `0027_quality_artifact_stages`: preserve one canonical CARE quality identity while appending independently audited minimal/full-scale stage artifacts without overwriting history
- `0028_read_audit_pipeline`: move minimized business-read attribution to a bounded Redis stream, batch it into monthly PostgreSQL partitions, and compress/purge it under explicit retention

`docker-compose.yml` is a local, production-shaped dependency stack (including
Neo4j Community), not a
production deployment. Its services bind to localhost and do not replace TLS,
secret management, backups, ingress policy, or PostgreSQL/Redis/MinIO release
integration tests.

`Dockerfile` and `deploy/kubernetes/` provide the production application
baseline: a non-root multi-stage image, three API replicas, independent
Dramatiq workers, a durable outbox relay, one-time migration Job, dedicated
read-audit batch/retention workers, readiness and liveness probes, resource
bounds, HPA, disruption budget, default-deny network
policy and scheduled verified backups. The checked-in digest is intentionally
non-deployable. Follow `deploy/README.md` to inject the exact signed image digest
and secret-manager-backed runtime configuration; the local Compose stack is
never an allowed production substitute. Run `windops-deployment-policy` against
the final rendered manifests to produce the content-addressed deployment-policy
report; it enforces immutable images, restricted pod security, destination-scoped
egress and an approved encrypted backup StorageClass.

## Install and run

```powershell
cd C:\coding\project\wind-agent\backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test,dev]"
alembic upgrade head
dramatiq windops_backend.workers
windops-outbox-relay
windops-read-audit-worker
uvicorn windops_backend.main:app --host 0.0.0.0 --port 8000
```

The read-audit retention contract keeps hot rows for 30 days, then atomically
compresses deterministic JSONL batches into `read_access_audit_archives`. The
daily `windops-read-audit-maintenance` Job creates three months of future
partitions, archives bounded batches and deletes compressed archives only after
365 days. Both thresholds, queue capacity and batch sizes are runtime-validated;
retention must always exceed the archive age.

Set production values through the environment/secret manager, including
`WINDOPS_ENVIRONMENT=production`, `WINDOPS_AGENT_MODE=litellm`,
`WINDOPS_EMBEDDING_MODEL`, an external HTTPS `WINDOPS_MINIO_PUBLIC_BASE`, TLS
URLs, Sites identity-role mappings, the gateway delegation secret, a metrics token,
trusted hosts and rate-limit policy. Production rejects blank model identifiers,
static role-key authentication, localhost/insecure public MinIO bases and example credentials. See
`example.env` for names, not deployable credentials.

LiteLLM calls are bounded by `WINDOPS_LITELLM_TIMEOUT_SECONDS` and
`WINDOPS_LITELLM_MAX_RETRIES`. Outputs must pass strict schema, evidence-grounding,
component-scope, confidence, recommendation-safety, and review-coverage gates. Provider
or evaluation failure is fail-closed and never falls back to deterministic demo reasoning.

## Observability and recovery

Production configuration requires OTLP-over-HTTPS tracing and a dedicated
32-plus-character metrics bearer token. `/metrics` exposes fixed route-template
HTTP counters/histograms, durable Mission and AgentExecution counts, telemetry
freshness, and runtime-validated SLO targets. `/metrics/slo` exposes the same
targets for machine verification. The production `/readyz` probe verifies
PostgreSQL, Redis, all five governed MinIO buckets, and Neo4j; `/healthz` remains
a process-liveness probe only. Collector and Prometheus rule examples live in
`ops/`, with multi-window error-budget alerts and runbooks under
`../docs/runbooks/`.

Recovery commands are intentionally separate from application startup:

```powershell
windops-backup --output-dir D:\windops-recovery
windops-restore --bundle D:\windops-recovery\windops-backup-<timestamp> `
  --confirm-target <exact-database-name>
windops-dr-drill --output-dir D:\windops-drills\2026-Q3 `
  --confirm-target <isolated-drill-database-name>
```

The backup bundle contains a custom-format PostgreSQL dump, current objects
from the four authoritative MinIO buckets, a non-secret configuration snapshot,
Alembic revision, row-count invariants, and SHA-256 for every artifact. Restore
validates the complete bundle and target isolation before mutation, then reads
back every object and database invariant. See
`../docs/runbooks/backup-recovery.md`; never run a restore against a live target
without an approved change and traffic isolation.

Neo4j is a disposable read projection, never the transaction authority. Raw
SCADA samples remain in TimescaleDB; the graph stores sensor identities,
semantic anomalies, diagnoses, evidence, decisions, work orders, resources and
closed-loop cases. Production requires `WINDOPS_NEO4J_URI=neo4j+s://...` and
external credentials. Projector events are replay-safe because each run builds
the named projection from current PostgreSQL state.

## API surface

All routes use `/api/v1`. Key endpoints include idempotent `POST /scada/ingest`,
idempotent `POST /missions`, filterable turbine/alarm/Mission/work-order/resource
collections, mission/alarm/evidence/decision/execution reads, revision-guarded alarm
acknowledgement/assignment and Mission approval, governed work-order reads, ordered
task completion, resumable filtered domain-event SSE, health, knowledge cases,
the authenticated database-backed knowledge-document endpoint, versioned
`/catalog` and `/tools`, plus `/observability/agent-executions/24h`. The latter
reports success/failure/running counts, latency, tool/token totals, per-node
aggregates and bounded public failure context. In test mode only,
`outbox_inline_drain=true` makes the request explicitly drain events so
deterministic end-to-end tests can assert the final state. This setting is
rejected outside tests.

Knowledge graph endpoints are available under `/knowledge-graph`: `summary`,
generic `entities/{id}/subgraph`, pgvector-plus-Neo4j `search`, turbine
`fault-trace`, alarm `impact`, failure mode `similar-cases`, passage
support/contradiction analysis, `observability`, `reconcile`, and the
operations-manager-only `reindex` and `rebuild` commands.

## Quality gates

```powershell
python -m pytest tests -q
python -m ruff format --check src tests alembic
python -m ruff check src tests alembic
python -m mypy --no-incremental src
alembic upgrade head --sql
python -m bandit -q -r src
python -m pip_audit
```

The SQLite suite verifies idempotency, outbox creation/draining, stale-lease
recovery and old-worker fencing, independent failure audit, revision/escalation
continuations, read attribution, persisted catalog versions, 24-hour
observability, HITL/RBAC gates, generic command idempotency, custom/default
work-order plans, atomic resource reservation, JSON Schema measurement
thresholds, artifact hash gating, measured health/case closure, and
master-only reference import. The graph suite additionally verifies unique
identities, relationship integrity, raw-SCADA exclusion, outbox projection,
stale-writer fencing, idempotent rebuild, reconciliation, typed Neo4j batches,
hybrid vector/graph retrieval, support-versus-contradiction analysis and a
complete closed-loop case/resource path. A release still needs integration
gates against real PostgreSQL/Timescale/pgvector, Redis/Dramatiq, MinIO, Neo4j
and LiteLLM.

The repository suite intentionally skips the external release test unless
`WINDOPS_RUN_EXTERNAL_RELEASE_TESTS=1` is set in an isolated production-shaped
environment. A release is blocked until that test, a real restore drill, DAST,
and browser accessibility/visual acceptance produce retained evidence. Follow
`../docs/runbooks/release-acceptance.md`; a skipped gate is not a pass.
