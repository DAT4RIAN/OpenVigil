# WindOps Python backend — WT-023 durable vertical slice

This Python 3.12 service implements the audited operational chain:

```text
SCADA ingest → durable outbox → LangGraph analysis → human review
→ approval-gated work order → five ordered, evidenced field tasks
→ health 68→82 / main-bearing 63→78 → resolved alarm → knowledge case
```

## Runtime boundary

Production requires PostgreSQL/asyncpg with TimescaleDB and pgvector, Redis with
Dramatiq, MinIO, and LiteLLM. Production configuration rejects SQLite, runtime
schema bootstrap, demo seed, deterministic reasoning, non-TLS database/Redis/
MinIO connections, example secrets, and inline outbox draining. SQLite and the
in-memory artifact verifier are explicitly test-only.

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
subject headers are ignored, every read writes a `read_access_audits` row, and
the test-only explicit bypass is rejected outside `WINDOPS_ENVIRONMENT=test`.
Actor names in JSON are ignored; approval and field evidence identity comes
from the authenticated principal.

| Operation           | Required role          |
| ------------------- | ---------------------- |
| SCADA ingest        | `scada_ingestor`       |
| approve / reject    | `operations_approver`  |
| request revision    | `maintenance_reviewer` |
| escalate            | `operations_manager`   |
| complete field task | `field_technician`     |

Production reference data is never loaded automatically. After applying
Alembic, an operations manager can explicitly import the controlled master-data
pack (farm, WT-023, knowledge document, resources, weather window):

```powershell
windops-reference-import --reference-pack wt023
```

The command securely prompts for the operations-manager API key. It creates no
alarm, mission, decision, approval, work order, or agent execution. It also
loads a versioned Agent/Skill/Tool catalog. The controlled manual body lives in
PostgreSQL with a canonical `windops://knowledge/documents/{id}` citation;
provider embeddings are persisted there when vectorization runs. The importer
does not pretend to have uploaded a MinIO knowledge object.

`request_revision` records the review result, queues a new durable analysis,
reopens the Decision proposal and returns to a new revision-guarded review.
`escalate` keeps the Decision open and increments the revision, so a later
approve/reject/revise action remains valid. Neither result can be reused as the
approval that authorizes a work order.

## Field evidence gate

Tasks must complete in sequence 1–5. Every completion requires:

- `artifact_uri`
- `artifact_sha256` (64 hexadecimal characters)
- a non-empty structured `measurement`
- authenticated `verified_by` identity (server-owned)

Each task has an extra-forbidden, versioned business schema and closure limit:

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
are impossible until exactly five verified, schema-valid task-evidence records
exist.

## Architecture and migrations

- FastAPI routes and Pydantic wire models
- SQLAlchemy async persistence and 11 domain tool adapters
- public LangGraph state only (no hidden chain-of-thought storage)
- LiteLLM schema-constrained production reasoning
- `AgentExecution`, Evidence, Decision, Approval and resource ledgers
- versioned Agent/Skill/Tool definitions and execution-to-version links
- `0001_wt023`: base domain, Timescale hypertable, pgvector index
- `0002_domain_audit`: structured evidence/decision/execution audit
- `0003_durable_execution`: transactional outbox and field-task evidence
- `0004_operational_hardening`: fencing leases, read attribution, catalog/version links

`docker-compose.yml` is a local, production-shaped dependency stack, not a
production deployment. Its services bind to localhost and do not replace TLS,
secret management, backups, ingress policy, or PostgreSQL/Redis/MinIO release
integration tests.

## Install and run

```powershell
cd C:\coding\project\wind-agent\backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test,dev]"
alembic upgrade head
dramatiq windops_backend.workers
windops-outbox-relay
uvicorn windops_backend.main:app --host 0.0.0.0 --port 8000
```

Set production values through the environment/secret manager, including
`WINDOPS_ENVIRONMENT=production`, `WINDOPS_AGENT_MODE=litellm`,
`WINDOPS_EMBEDDING_MODEL`, an external HTTPS `WINDOPS_MINIO_PUBLIC_BASE`, TLS
URLs and all five role keys. Production rejects blank model identifiers,
localhost/insecure public MinIO bases and example credentials. See
`example.env` for names, not deployable credentials.

## API surface

All routes use `/api/v1`. Key endpoints include idempotent `POST /scada/ingest`,
mission/alarm/evidence/decision/execution reads, revision-guarded mission
approval, work-order reads, ordered task completion, health, knowledge cases,
the authenticated database-backed knowledge-document endpoint, versioned
`/catalog` and `/tools`, plus `/observability/agent-executions/24h`. The latter
reports success/failure/running counts, latency, tool/token totals, per-node
aggregates and bounded public failure context. In test mode only,
`outbox_inline_drain=true` makes the request explicitly drain events so
deterministic end-to-end tests can assert the final state. This setting is
rejected outside tests.

## Quality gates

```powershell
python -m pytest tests -q
python -m ruff format --check src tests alembic
python -m ruff check src tests alembic
python -m mypy --no-incremental src
alembic upgrade head --sql
```

The SQLite suite verifies idempotency, outbox creation/draining, stale-lease
recovery and old-worker fencing, independent failure audit, revision/escalation
continuations, read attribution, persisted catalog versions, 24-hour
observability, HITL/RBAC gates, atomic resource reservation, task-specific
measurement thresholds, artifact hash gating, health/case closure, and
master-only reference import. A release still needs integration gates against
real PostgreSQL/Timescale/pgvector, Redis/Dramatiq, MinIO and LiteLLM.
