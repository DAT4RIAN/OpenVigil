# OpenVigil Architecture

本文件描述当前代码库的真实架构，而不是目标架构提案。基线为工作树 `2026-09-04`、Git `HEAD 8fd126672776aff6c52328a621391e4f8747627a`。已知实现缺口以 `AUDIT_REPORT.md` 为准；本文件只在相关边界处标出 Issue ID，避免把计划状态写成已完成事实。

## 1. System Context

OpenVigil 是一个面向风电运维的双运行时系统：同一套 vinext/React 页面既可运行确定性 Demo，也可通过 OpenAI Sites Worker 接入 Python 生产后端。生产侧是一个模块化 FastAPI 单体，使用 PostgreSQL/TimescaleDB 作为权威业务账本，并通过 Redis/Dramatiq、MinIO、Neo4j、LiteLLM、模型推理服务和 EAM 集成形成异步闭环。

系统没有把 Demo 数据库当成生产数据库，也没有让浏览器直接访问 PostgreSQL、Redis、MinIO 或 Neo4j。

```text
Browser / ChatGPT user
        |
        v
OpenAI Sites + vinext Worker
  - document auth gate
  - production route boundary
  - per-user delegated JWT
  - backend allowlist / timeout / body limit
        |
        v
FastAPI API (authoritative control plane)
  |          |             |             |
  v          v             v             v
PostgreSQL  Redis         MinIO         Neo4j
/Timescale  /Dramatiq     artifacts     derived graph
  |
  +--> durable outbox --> relay --> workers --> LiteLLM / model runtime / EAM
```

## 2. Runtime Modes

### 2.1 Demo mode

- Entry: `worker/index.ts` + vinext App Router.
- Persistence: Cloudflare D1 binding `DB`; `.openai/hosting.json` declares the binding.
- Schema: `db/schema.ts` plus seven Drizzle migrations under `drizzle/`.
- Data: deterministic fixtures and the WT-023 demo workflow in `lib/`, with server-side D1 stores under `db/`.
- Realtime: finite deterministic `/ws/*` handlers and demo event streams.
- Purpose: product demonstration and interaction development. It is not production evidence and may contain explicitly labelled synthetic predictions.

### 2.2 Production mode

- Selected by `WINDOPS_RUNTIME_MODE=production` in `lib/production-runtime.ts`.
- The Worker rejects unmigrated fixture APIs and simulated WebSockets instead of falling back to Demo.
- Production documents are authenticated before business rendering. The Worker calls `/api/v1/session`, converts the server-owned role/scope/capability response to a sanitized internal header, and the React shell consumes only that contract.
- Browser API requests are translated by route adapters or proxied through `/api/backend/[...path]` to a strict backend path allowlist.
- Each upstream request receives a short-lived HMAC Sites delegation JWT bound to subject, method, full target, body SHA-256 and a unique `jti`.
- The Worker requires a valid backend release ID and image digest on responses. It parses the commit header but does not compare it with configured release state (`TECH-M002`).

Demo D1 and production PostgreSQL are intentionally separate bounded contexts. Data is not replicated between them.

## 3. Frontend And Gateway

### 3.1 Page layer

`app/` contains 22 product routes. `components/pages/` owns page composition, `components/layout/` owns the application shell, and `components/data-display/`, `components/charts/` and `components/ui/` contain reusable presentation primitives.

TanStack Query owns production query lifecycle. Zustand and the demo workflow helpers are used for local/demo interaction state. Three.js is confined to the digital-twin viewer; ECharts is used for operational charts.

The production homepage is backed by one aggregate endpoint, `/api/v1/dashboard`, while other workspaces use domain-specific collection/detail endpoints. Several pages still collapse pending/error into empty or zero-valued presentation (`TECH-H001`, related to `UI-H-002` and `UI-H-003`).

### 3.2 API adapters

There are three frontend API patterns:

1. Demo-only App Router handlers read fixtures or D1.
2. Production domain adapters in `lib/production-domain-adapter.ts` translate FastAPI snake_case envelopes into the existing UI contracts.
3. `app/api/backend/[...path]/route.ts` delegates an already-authorized backend path to the common production gateway.

`lib/api-client.ts` provides typed GET/POST helpers, publishes authentication/authorization/backend/network failures, and retries a transport-failed POST once with the same idempotency key and body.

### 3.3 Realtime

Production realtime uses `/api/v1/events/stream` Server-Sent Events. Event cursors are monotonic integers for unrestricted principals and signed opaque cursors for scoped principals. The client persists only the non-sensitive cursor and performs bounded reconnect. Production deterministic `/ws/*` endpoints fail closed.

## 4. Backend Boundaries

### 4.1 Application structure

The backend package is `backend/src/windops_backend/`:

- `main.py`: application/lifespan, middleware, error envelopes, metrics and router registration.
- `api/`: HTTP transport, authentication dependencies and response serialization.
- `services/`: domain operations, idempotent commands, reports, operational views, model runtime and integrations.
- `agents/`: governed reasoning and review orchestration.
- `knowledge_graph/`: Neo4j projection/query layer.
- `benchmarks/care/`: CARE contract, quality, scoring, import, evaluation, replay, online inference and full-scale CLI pipeline.
- `models.py` / `storage.py`: SQLAlchemy entities.
- `workers.py` / `outbox.py`: Dramatiq actors, durable claims and relay.
- `operations/`: backup, restore, release evidence, deployment policy and release smoke tools.

The API process never treats Neo4j as authoritative. PostgreSQL writes domain state and outbox rows transactionally; workers may rebuild graph projections from that source.

### 4.2 Domain model

The main production aggregates are:

- tenant, wind farm and turbine;
- ingest source/receipt/stream state, SCADA sample and quarantine;
- alarm, mission, evidence, diagnosis/decision, approval and work order;
- resource, reservation and weather window;
- agent/skill/tool catalog, execution and tool invocation;
- knowledge document/case and graph projection events;
- registered model, deployment and prediction;
- generated report;
- CARE dataset/file/event/feature/quality/evaluation/result/metric/replay/policy state;
- command receipt, delegated nonce/audit, read audit, domain event and outbox event.

### 4.3 Error contract

Domain errors, HTTP errors and Pydantic validation errors are returned as structured JSON with a stable code and message. Unexpected exceptions remain 500 responses. Gateway transport errors are normalized separately as authentication, authorization, backend, timeout or network failures.

## 5. Authoritative Data And Storage

### 5.1 PostgreSQL / TimescaleDB / pgvector

PostgreSQL is authoritative for production business state. TimescaleDB stores bounded SCADA history and pgvector stores knowledge embeddings. The continuous Alembic graph has one current head: `0026_schema_contract_alignment`.

SQLite schema bootstrap exists only for automated tests. It is not an accepted production substitute.

### 5.2 Redis and durable execution

Redis is both the Dramatiq broker and production rate-limit store. Business mutations create durable outbox rows in the same transaction as aggregate changes. A separate relay scans pending or visibility-expired rows and dispatches actors. Leases, fencing tokens and retry-aware terminal state prevent an old worker from overwriting a newer claim.

### 5.3 MinIO

Production configuration requires separate buckets for field evidence, knowledge documents, model artifacts, digital-twin artifacts and CARE artifacts. Presigned uploads are verified server-side before a database row becomes authoritative. CARE has isolated prefixes and separate normal-worker versus break-glass cleanup policies.

### 5.4 Neo4j

Neo4j contains a derived, rebuildable knowledge graph. Raw SCADA is not projected. Nodes and relations retain tenant/farm/turbine/entity/data-scope attributes, and scoped queries are filtered by `GraphAccessPolicy`.

## 6. Primary Data Flows

### 6.1 SCADA to incident

```text
source credential + ordered batch
  -> /scada/ingest
  -> source policy / schema / sequence / quality validation
  -> receipt + samples + domain event
  -> health / predictive or anomaly evaluation
  -> Alarm
  -> Mission outbox event
  -> Dramatiq diagnosis/review
  -> Decision + human approval
  -> WorkOrder + EAM outbox publish
  -> field evidence / closure / knowledge case
```

Ingest receipts and stream state provide deduplication, monotonic sequence handling, late-data visibility and bounded quarantine.

### 6.2 Human-governed command

The Worker signs the exact request. FastAPI authenticates the delegated identity, consumes the write nonce in an independent transaction, authorizes role plus scope, then executes a subject/command/target/idempotency-key command receipt in the business transaction. Optimistic aggregate revisions reject stale writers. A client transport retry uses the same business idempotency key but receives a fresh delegation assertion.

### 6.3 Knowledge ingestion and retrieval

The API verifies a presigned object, commits the knowledge document and indexing outbox event, and a worker extracts/chunks/embeds it through the configured provider. Retrieval combines PostgreSQL/pgvector passages with the scoped Neo4j projection and returns citations. No raw object is trusted merely because the browser supplied a URI.

### 6.4 Model and CARE flow

The regular model registry supports artifact verification, staging, activation, inference, prediction provenance and rollback. Anomaly activation additionally requires server-issued CARE evaluation authorization. The public activation/rollback path does not currently construct that authorization, and the production gateway blocks two anomaly execution endpoints (`CARE-C005`).

CARE itself is a batch/offline pipeline:

```text
read-only CARE source
  -> source contract
  -> quality contract and masks
  -> columnar import / MinIO artifacts
  -> offline/full-scale evaluation
  -> PostgreSQL benchmark metadata
  -> selected replay
  -> anomaly prediction / alert policy / Mission chain
```

The code declares this work to require an independent worker and the optional `benchmark` dependency group. The production image and Kubernetes baseline do not currently supply that execution plane (`CARE-H008`, `CARE-H009`, `TECH-H003`).

## 7. Authorization And Security

- Production human auth mode is Sites delegation; static human tokens are development-only.
- Roles and asset/data scopes are server configured. Missing production scope fails closed.
- `require_roles` protects bounded business writes; `require_global_roles` additionally requires `allow_global`, no restricted entity list and the appropriate data domain.
- SQLAlchemy `do_orm_execute` criteria apply row scope to registered SELECT models. Write endpoints must load their scoped aggregate before mutation.
- Every business read currently inserts and commits a `ReadAccessAudit` row before performing the read (`TECH-M004`).
- Metrics require a dedicated bearer token. Docs/OpenAPI are disabled by production configuration.
- Trusted hosts, request-size limits, Redis rate limits, security headers, TLS-only dependency configuration and non-root/read-only containers are enforced in production.
- Secrets are loaded from environment/secret manager references; checked-in examples contain only development placeholders.

## 8. Deployment Topology

### 8.1 Sites

The frontend is built with vinext/Vite and deployed through Sites. `.openai/hosting.json` binds the Demo D1 database. Production requires backend origin, delegation secret, expected release ID and expected image digest.

### 8.2 Backend Kubernetes baseline

`backend/deploy/kubernetes/` defines:

- three API replicas with startup/readiness/liveness probes;
- two general Dramatiq workers;
- one durable outbox relay;
- a one-time Alembic migration Job;
- a backup CronJob, PDB/HPA, Service and default-deny network policy.

PostgreSQL, Redis, MinIO, Neo4j, LiteLLM, model serving, ingress, certificates and secret management are external managed dependencies. The checked-in manifests deliberately contain a non-deployable zero digest and require a release render step.

No CARE worker/Job is present in this baseline (`TECH-H003`).

### 8.3 Release evidence

The release workflow builds and pushes a digest-pinned backend image, signs and scans it, creates an SBOM, runs an image smoke, renders Kubernetes manifests, exercises a protected external environment and creates a backup. The repository also contains a verifier requiring 11 content-addressed gate reports.

The workflow does not currently assemble that manifest or call `windops-release-gate`; it writes its own `status: qualified` before DAST, accessibility/visual, SLO, Sites post-deploy, migration rollback and DR evidence exist (`TECH-H002`). Its image smoke runs the application in development mode (`TECH-H002`).

## 9. Verification Topology

- Frontend: production build, bundle budget, TypeScript, ESLint, Prettier, Node contract tests and Playwright.
- Backend: Pytest with coverage budgets, Ruff, strict mypy, Bandit, pip-audit and Alembic render/head checks.
- PostgreSQL CI: migration, concurrency, service resilience and prediction-lock external tests.
- Cross-layer CI: Sites Worker + TLS FastAPI + PostgreSQL identity/rotation path.
- Release: image/signature/scan/SBOM/manifests/external dependency/backup candidate checks.

Current limitations:

- CARE PostgreSQL external suites and the optional benchmark dependency are absent from required CI (`CARE-H008`, `CARE-H009`).
- Browser coverage is one Chromium project and does not establish the UI acceptance matrix (`TECH-M003`, related to `UI-M-002`).
- The official CARE reference is a mapped, immutable Git submodule pinned to the reviewed
  `EnergyFaultDetector` `v0.6.2` commit. CI performs a recursive checkout and runs the
  fail-closed reference verifier, which binds the submodule URL, commit, tree, MIT license,
  selected source-file hashes, canonical UTF-8/LF source-of-truth document hashes and
  golden-vector comparison into a content-addressed evidence report (`CARE-H010`). Production
  imports no runtime code from the reference submodule.

## 10. Architectural Invariants

Any implementation change must preserve these boundaries:

1. Demo data must never silently appear in Production.
2. PostgreSQL is authoritative; Neo4j and caches are rebuildable projections.
3. High-risk actions require server-owned identity, capability, scope and human approval where specified.
4. Side effects require idempotency and must not be inferred from a transport response alone.
5. Artifacts are verified by content identity before their metadata becomes authoritative.
6. CARE truth cannot enter model input, and CARE-derived output must retain provenance/license metadata.
7. A release is not accepted until the complete evidence manifest passes the final release verifier.
