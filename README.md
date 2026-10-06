<p align="center">
  <img src="public/images/openvigil-logo.png" alt="OpenVigil" width="140">
</p>

<h1 align="center">OpenVigil</h1>
<p align="center"><b>English</b> · <a href="README-CN.md">简体中文</a> · <a href="README-DE.md">Deutsch</a> · <a href="README-ES.md">Español</a> · <a href="README-FR.md">Français</a> · <a href="README-JA.md">日本語</a> · <a href="README-KO.md">한국어</a> · <a href="README-IT.md">Italiano</a></p>
<p align="center"><b>Multi-agent platform for intelligent wind operations and maintenance</b><br>Connect monitoring, diagnosis, human decisions, and field execution in an auditable workflow.</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-Apache%202.0-blue" alt="Apache License 2.0">
  <img src="https://img.shields.io/badge/React-19.2-61DAFB?logo=react&logoColor=111827" alt="React 19.2">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/status-production%20candidate-f59e0b" alt="Production candidate">
</p>

<p align="center">
  <a href="#installation">Installation</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#features">Features</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#model-configuration">Model configuration</a> ·
  <a href="#development">Development</a> ·
  <a href="#license">License</a>
</p>

---

<p align="center">
  <img src="public/openvigil-command-center.png" alt="OpenVigil Operations Command Center" width="960">
</p>

> _Wind operations data is often scattered across assets, SCADA, alarms, models, human approvals, work orders, and field evidence. The challenge is to give every judgment a source, every decision an accountable owner, and every action a verifiable outcome._
>
> _OpenVigil connects “monitoring → alarms → Mission → diagnosis → human decisions → work orders → field evidence → health reassessment → knowledge updates” into a traceable, recoverable workflow governed by permissions. AI organizes evidence and proposes alternatives; people authorize high-risk actions._

## Project status

> [!IMPORTANT]
> OpenVigil is currently a **production candidate implementation**, not a system already deployed in production. The default `demo` mode provides deterministic product demonstrations. `production` mode connects to an independently deployed Python backend that holds authoritative state and fails closed when identity, configuration, dependencies, or APIs do not meet requirements. Real wind farms, field systems, model providers, and release environments still require joint acceptance testing.

The product is positioned as an intelligent platform for wind operations and maintenance. Login imagery and the Demo wind farm illustrate a scenario; they do not define the product's scope or prove field integration or production acceptance.

## Installation

### Requirements

- Node.js `>= 22.13.0`
- pnpm `11.21.0`, preferably managed through Corepack
- Python `3.12.x`, required only for `backend/`
- Docker Compose, optional for starting local Python backend dependencies

### Get the code

```bash
git clone --recurse-submodules https://github.com/DAT4RIAN/OpenVigil.git
cd OpenVigil

corepack enable
pnpm install --frozen-lockfile
```

The repository uses `pnpm-lock.yaml`. Do not generate or commit `package-lock.json`, or mix npm and pnpm lockfiles in one change.

## Quick start

### Product demo

```bash
pnpm dev
```

Open `http://localhost:3000`. The default Demo includes 64 deterministic turbine assets, the WT-023 main-bearing anomaly scenario, D1 workflow state, finite SSE streams, simulated WebSockets, and an Agent runtime with 16 tools. It supports product demonstrations, screenshots, and regression checks.

### Production build

```bash
pnpm build
pnpm start
```

`pnpm start` serves the same build artifact used for release. It still defaults to Demo. Production mode requires a configured Sites Worker, Python backend address, delegated identity, approved release ID, and image digest. Routes that have not been migrated do not fall back to fixtures.

### Python backend vertical slice

Run the following commands in Windows PowerShell. The root `.env` is the single local configuration file; create it from `.env.example` only if it does not already exist.

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }

cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test,dev,structural]"

docker compose up -d
alembic upgrade head
windops-reference-import --reference-pack wt023
```

The current sole migration head is `0032_structural_workflow`. From `backend/`, run `python scripts/verify_migration_head.py` to check the migration graph and documented declarations.

The reference import prompts for the `operations_manager` key. Then start the outbox relay, Dramatiq worker, read-audit worker, and API in four separate terminals:

```powershell
windops-outbox-relay
dramatiq windops_backend.workers
windops-read-audit-worker
uvicorn windops_backend.main:app --host 127.0.0.1 --port 8000
```

### Repeatable local startup on Windows

After installing frontend dependencies and creating `backend/.venv`, run these commands from the repository root:

```powershell
./scripts/Start-Local.ps1
./scripts/Status-Local.ps1
./scripts/Stop-Local.ps1
```

The first startup defaults to frontend port `3000` and API port `8000`. Use `-FrontendPort 3180 -ApiPort 8180` to select available ports. Subsequent starts reuse the saved ports and verify existing services before creating processes. A port conflict or mismatched process identity stops the operation; the scripts do not terminate the process occupying the port.

This is an isolated development stack. The frontend remains in Demo, and the independent Python backend uses `development / deterministic / static_tokens`. It does not establish production gateway connectivity or real-model acceptance. The scripts derive a separate Compose project from the repository path and use PostgreSQL `25432`, Redis `26379`, MinIO `29000/29001`, and Neo4j `27474/27687`, with all ports bound to loopback addresses.

Generated local credentials, Compose configuration, process identities, and logs are stored in the ignored `.artifacts/local-stack/` directory. This configuration belongs to the isolated startup workflow: it does not read or overwrite the user's root `.env` or automatically import reference data. Ordinary manual startup continues to use the root `.env`. Do not share or commit this artifact directory.

Startup waits for dependencies, applies Alembic migrations, builds the frontend, and starts the API, Dramatiq, outbox relay, read-audit worker, and frontend. Status checks verify the migration head, Redis, five MinIO buckets, Neo4j, API authentication, read-audit persistence for the current request, and the login page. Failures preserve dependencies, data, and process logs for diagnosis. `Stop-Local.ps1` verifies PID, creation time, command, and repository ownership before stopping the corresponding processes and Compose project; containers, credentials, and data volumes are retained.

After changing stylesheet entry points or database migrations, run `pnpm check:architecture --write` and review the updated architecture inventory. `pnpm check:architecture` and CI reject an outdated inventory.

## Features

### Operations command center

The home page combines fleet KPIs, a health matrix, power trends, high-priority alarms, active Missions, and Agent Activity to show what is happening across the wind farm and what AI is working on.

### Operations workflow

```text
SCADA / CMS / weather / manual alarms
              │
              ▼
       Alarm → Mission
              │
              ▼
  Multi-agent evidence and diagnosis
              │
              ▼
  Alternatives and human approval
              │
              ▼
  Work Order → ordered field tasks
              │
              ▼
  Health reassessment → knowledge update
```

The WT-023 Demo scenario follows the full path from abnormal main-bearing vibration and temperature through Mission creation, diagnosis, alternative comparison, approval, a work order, five field tasks, health recovery, and knowledge capture. All writes carry idempotency keys, correlation IDs, expected revisions, and append-only audit events.

Executable recommendations in the Python backend must bind to the current Mission's governed work template through `execution_plan_id`, and actions must match that template. Templates come from `analysis_profile.work_order_plan` or the server's default inspection template; their content and asset scope determine the binding identifier. Missing, unknown, stale, or mismatched bindings return 409 during approval. Older unbound decisions require revision. Unbound recommendations such as replacement can remain available for discussion, but they are not silently converted into inspection work orders. Tasks, measurement thresholds, safety requirements, duration, and closure rules always come from the governed template.

The five AI review types share an explicit `review_target` that records the candidate alternative and work template being reviewed. Reviews assess execution of that maintenance plan. Preconditions are stored in `conditions`, and turbine operating restrictions in `operating_constraints`; a review does not grant permission to operate, and execution still requires human approval. Valid failed reviews are preserved, and historical reviews without an explicit target are not automatically upgraded to verified new reviews.

The real-model execution ledger records the request digest, message size in UTF-8 bytes, and output token configuration in `evaluation_result.request`, without storing the request body. Responses also record the finish reason and public response size. Responses marked as truncated by the provider are rejected even if they parse as JSON. When a later node fails or the business transaction rolls back, `completed_node_usage` in the failure record preserves usage, model identity, and latency from earlier successful model nodes in that attempt; rolled-back decision outputs are not retained. Unknown usage for a failed node prevents the attempt's cost from being considered complete or free. Missing historical records are not fabricated.

### Business workspaces

| Workspace                 | Route                                | Main capabilities                                                                          |
| ------------------------- | ------------------------------------ | ------------------------------------------------------------------------------------------ |
| Operations Command Center | `/`                                  | Fleet status, risk objects, Missions, and Agent activity                                   |
| Wind Farm / Turbine       | `/wind-farms`, `/turbines/:id`       | Asset topology, health, SCADA, alarms, and maintenance context                             |
| SCADA / Alarm             | `/scada`, `/alarms`                  | Time-series monitoring, thresholds, quality codes, anomalies, and handling status          |
| Agent / Mission           | `/agents`, `/missions`               | Agent organization, task queues, evidence, collaboration timelines, and approval readiness |
| Decision / Work Order     | `/decisions`, `/work-orders`         | Alternative comparison, human approval, task gates, and field evidence                     |
| Health / Predictive       | `/health`, `/predictive-maintenance` | Health matrices, risk ranking, RUL display, and maintenance windows                        |
| Resource / Maintenance    | `/resources`, `/maintenance`         | Crews, spare parts, tools, weather windows, calendars, and conflict checks                 |
| Knowledge / Reports       | `/knowledge`, `/reports`             | Evidence retrieval, knowledge cases, report previews, and PDF/DOCX export                  |
| Data / Models / Diagnosis | `/data`, `/models`, `/diagnosis`     | Data governance, CARE evaluation, model gates, and diagnosis provenance                    |
| Digital Twin / Settings   | `/digital-twin`, `/settings`         | 2D operational views, runtime status, identity, and data policies                          |

The digital twin page provides operational context. It does not claim physical simulation, real-time control, or an engineering-grade 3D model.

### Multi-agent collaboration

The Demo's 22 Agents are organized into three layers:

| Layer     | Representative roles                                                              | Responsibilities                                                            |
| --------- | --------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| Decision  | SCADA Analysis, Vibration Diagnosis, Predictive Maintenance, Maintenance Strategy | Detect anomalies, organize evidence, and propose diagnoses and alternatives |
| Review    | Safety, Engineering, Economic, Compliance, Resource Review                        | Review safety, engineering, economics, compliance, and resource conditions  |
| Execution | Work Order, Crew, Spare Parts, Maintenance, Report, Knowledge                     | Turn approved decisions into governed execution and feedback                |

The Python backend uses an independent LangGraph workflow and a governed SQL tool catalog. The UI and APIs expose only public, structured, auditable evidence and conclusions. They do not display or fabricate a model's hidden Chain-of-Thought.

### Onshore hybrid tower operations

The production workspace at `/structural` connects tower components, tendons, calibrated channels, original waveforms, direct force measurements, a dedicated analysis queue, and health baselines. Original objects are checked by SHA-256. pyOMA2 FDD retains quality exclusions, modes, and unquantified uncertainty; tower modes cannot estimate uncalibrated absolute tendon force.

Modal drift and direct prestress scenarios reuse Missions, independent engineering review, approvals, retest work orders, health review, and pending knowledge cases. Procedure passages retain original locations. Graph statement reads revalidate scope, approved revisions, and original sources; insufficient data, withdrawal, expiry, and source drift prevent consumption.

Analyses freeze algorithm, execution code, configuration, and calibration identities. A hybrid deployment also freezes both API and structural image digests and their release bundle. Result hashes survive PostgreSQL JSONB roundtrips. Image fields are explicitly deployment declarations and remain `unbound` when absent; independently observed runtime identity still requires deployment and signature evidence.

Local software acceptance uses synthetic signals, test identities, and deterministic reasoning. Real SHM, tower parameters, calibration, authorized procedures, and responsible field personnel remain pending; field and formal release qualification remain unverified. See [execution progress](EXECUTION_PROGRESS.md) for implementation and evidence.

### CARE v6 benchmark

CARE v6 provides a separate offline anomaly-detection and governed evaluation path. Raw data is not included in the repository; operators must explicitly supply an authorized, read-only source.

| Area             | Current implementation                                                                                                                                         |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Data contract    | 95 events, 36 assets within their farms, 5,242,948 rows; fixed A → C → B import order                                                                          |
| Quality handling | Raw values remain unchanged; quality issues are recorded in a separate mask; ground truth becomes available to the evaluator only after predictions are frozen |
| Storage          | All signals are stored in partitioned wide-table Parquet; only selected, bounded replay windows enter the online time-series store                             |
| Evaluation       | Leave-one-asset-out evaluation within each farm, covering 36 folds, 95 events, and 281,249 prediction points                                                   |
| Governance       | Datasets, artifacts, models, evaluations, replays, and exports are bound to immutable identities, digests, and permissions                                     |
| Limits           | Current results do not support claims about generalization across farms, real RUL, 30-day failure probability, or field safety                                 |

The CARE dataset and derived distribution artifacts subject to its license follow CC BY-SA 4.0. The Apache License 2.0 for OpenVigil's own source code does not cover these data assets.

### APIs and real-time data

| Endpoint                                      | Purpose                                                                |
| --------------------------------------------- | ---------------------------------------------------------------------- |
| `/api/runtime`                                | Current runtime mode, backend readiness, and redacted release identity |
| `/api/workflow/:assetId`                      | Demo workflow snapshots, approvals, work orders, and audit state       |
| `/api/backend/:path+`                         | Allowlisted FastAPI gateway in production mode                         |
| `/api/v1/events/stream`                       | Production SSE with cursor resume and bounded reconnection             |
| `/ws/scada`, `/ws/alarms`, `/ws/agent-events` | Simulated Demo real-time channels; fail closed in production mode      |

For production requests, the Sites Worker issues short-lived delegated tokens for each user, binding the method, target, body digest, and unique `jti`. Browsers do not directly access PostgreSQL, Redis, MinIO, or Neo4j.

## Architecture

```text
Browser
   │
   ▼
vinext / React 19 application
   │
   ├── Demo
   │     └── Cloudflare Worker + D1
   │           ├── deterministic fixtures
   │           ├── workflow / audit state
   │           └── finite SSE + simulated WebSocket
   │
   └── Production
         └── Sites identity gateway
               │  delegated JWT / allowlist / release verification
               ▼
             FastAPI
               ├── PostgreSQL / TimescaleDB / pgvector
               ├── Redis / Dramatiq / durable outbox
               ├── MinIO governed artifacts
               ├── Neo4j derived knowledge graph
               ├── LiteLLM reasoning and embeddings
               └── SCADA / MQTT / HTTPS / EAM connectors
```

Demo D1 and production PostgreSQL are separate boundaries. There is no implicit data replication between them, and failed production queries cannot display Demo data as a fallback.

### Technology stack

| Layer   | Technologies                                                  |
| ------- | ------------------------------------------------------------- |
| Web     | React 19, TypeScript, vinext, Vite, Tailwind CSS              |
| Data UI | TanStack Query, TanStack Table, Zustand, ECharts, Three.js    |
| Edge    | Cloudflare Worker, D1, SSE, WebSocket                         |
| Backend | Python 3.12, FastAPI, Pydantic, async SQLAlchemy, LangGraph   |
| Async   | PostgreSQL transactional outbox, Redis, Dramatiq              |
| Data    | PostgreSQL, TimescaleDB, pgvector, MinIO, Neo4j               |
| AI      | LiteLLM, OpenAI-compatible providers, separate embedding path |
| Quality | Node test runner, Playwright, Pytest, Ruff, mypy, Bandit      |

Stable compatibility identifiers retain `windops_backend`, `WINDOPS_*`, `x-windops-*`, and the existing database, object-storage, and telemetry namespaces.

## Model configuration

All local model configuration belongs in the repository-root `.env`. The root `.env.example` is the only field template. Do not create another environment configuration in `backend/` or elsewhere.

Before enabling real reasoning, set:

```dotenv
WINDOPS_AGENT_MODE=litellm
WINDOPS_LLM_PROVIDER=siliconflow
```

Supported chat providers:

| `WINDOPS_LLM_PROVIDER` | Base URL variable                     | API key variable                      | Model variable              |
| ---------------------- | ------------------------------------- | ------------------------------------- | --------------------------- |
| `siliconflow`          | `WINDOPS_SILICONFLOW_BASE_URL`        | `WINDOPS_SILICONFLOW_API_KEY`         | `WINDOPS_SILICONFLOW_MODEL` |
| `bailian`              | `WINDOPS_BAILIAN_BASE_URL`            | `WINDOPS_BAILIAN_API_KEY`             | `WINDOPS_BAILIAN_MODEL`     |
| `deepseek`             | `WINDOPS_DEEPSEEK_BASE_URL`           | `WINDOPS_DEEPSEEK_API_KEY`            | `WINDOPS_DEEPSEEK_MODEL`    |
| `default`              | Existing LiteLLM/provider environment | Managed by the corresponding provider | `WINDOPS_LITELLM_MODEL`     |

Example:

```dotenv
WINDOPS_AGENT_MODE=litellm
WINDOPS_LLM_PROVIDER=siliconflow
WINDOPS_SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
WINDOPS_SILICONFLOW_API_KEY=
WINDOPS_SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V4-Flash
```

Alibaba Cloud Bailian defaults to `https://dashscope.aliyuncs.com/compatible-mode/v1`; DeepSeek defaults to `https://api.deepseek.com`. The `base_url` must use HTTPS without embedded credentials. Store API keys only in the ignored root `.env` or a production secret manager.

OpenCode Go is intended for coding Agent traffic. The current backend does not read `OPENCODE_GO_*`; `.env.example` retains only its reference address and variable names to avoid selecting it as a wind-diagnosis provider. Chat and embeddings use separate connection configurations. The application does not automatically reuse the chat endpoint or key for embeddings. If one provider account is authorized for both model types, its key may be configured separately at both entry points.

The existing vector store requires 1536 dimensions. Configure an OpenAI-compatible embedding service separately, for example a SiliconFlow Qwen model that supports this dimension count:

```dotenv
WINDOPS_EMBEDDING_MODEL=openai/Qwen/Qwen3-Embedding-4B
WINDOPS_EMBEDDING_API_BASE=https://api.siliconflow.cn/v1
WINDOPS_EMBEDDING_API_KEY=
WINDOPS_EMBEDDING_DIMENSIONS=1536
```

Put keys only in private local configuration or deployment secret management. Without the explicit endpoint, key, and dimension settings above, LiteLLM retains its default connection behavior. Explicit endpoints must use HTTPS without embedded credentials. Request parameters are sent to the real provider, and responses must contain complete, unique indices, 1536-dimensional vectors, and finite numeric values. Vectors are not padded or truncated. See the [SiliconFlow embedding API](https://docs.siliconflow.cn/docs/api/embeddings-post) for provider dimension capabilities.

Retrieval compares only vectors from the current embedding provider/model. After switching models, regenerate old vectors through the existing bounded automatic indexing path or the global knowledge administrator's `POST /api/v1/knowledge-graph/reindex`. Old vectors that have not been reindexed are excluded from ranking. Production joint acceptance uses the same connection configuration as indexing and querying.

### Real-model regression evaluation

Run from `backend/` with `.venv` activated. The command reads the existing LiteLLM configuration from the root `.env`, makes real provider calls, and incurs charges. Deterministic substitutes are not accepted.

```powershell
python -m windops_backend.operations.reasoning_eval --cases evaluations/wind-diagnosis-v1.json --pricing evaluations/siliconflow-v3.2-pricing.json --report ../.artifacts/improvements/reasoning-current.json
```

The six built-in synthetic engineering cases cover the main bearing, gearbox, temperature sensor, missing data, identity conflicts, and prompt injection in evidence text. Scoring checks failure classification, component, confidence, precision of supporting citations, recall of required citations, and explicit abstention; timeouts and errors do not count as abstention. Case labels, `required_evidence`, and `supporting_evidence` are excluded from model context. Optional `supporting_evidence` identifies additional valid citations; when absent, only required evidence is considered supporting. This small sample supports engineering regression of prompts and models. It cannot estimate real wind-farm diagnosis accuracy or prove that free-text conclusions are free from all semantic errors. Evaluation uses a separate prompt and public diagnosis output, rather than production workflow acceptance; the production confidence gate remains unchanged.

Reports retain every successful and failed case, end-to-end P95 including the first provider-library load, usage and cost for each attempt, unknown-cost counts, known-cost subtotals, case/prompt/code digests, Git state, and requested/returned model identities. Missing provider usage, model identity mismatch, or request timeout marks total cost as `UNVERIFIED`, rather than treating an attempt as a free success. Costs are estimates from a dated, sourced price table, without cache discounts; they are not billing records. Supply a matching price file when changing models.

Requests set `max_tokens=1024` and do not retry; an evaluation runs at most 50 cases from the case set. In the [SiliconFlow API](https://docs.siliconflow.cn/docs/api/chat-completions-post), this parameter limits the final response, excluding the model's internal thinking usage. `maximum_total_cost` is a stop threshold checked after receiving a response. The last request may exceed it, and it cannot account for charges the provider does not report. Use provider-side limits when a strict account budget is needed. The built-in six-case set uses a CNY 1 threshold. Any absolute gate failure saves the report and exits nonzero; failed cases are not deleted or automatically rerun until they pass.

Keep a reviewed report that passes the absolute gates, then add `--baseline <report-path>` for regression comparison. With matching case digests, report versions, and pricing currencies, classification, abstention, and citation metrics must not decrease; P95 and estimated cost may increase by at most 20%. An incompatible or failed baseline cannot produce a passing regression result. Real wind-farm cases require a separate case set reviewed by experts and labeled `expert-reviewed-field-cases`.

## Development

`docs/` is a local-only documentation directory and is excluded from Git commits and GitHub distribution. Root documents marked “local-only document” refer to materials available to maintainers with local copies; a clean clone does not include them. The artifact policy required by CI lives in `scripts/repository-artifact-policy.json` and prohibits tracking files under `docs/`. Repository formatting checks do not depend on the local documentation directory.

### Web

```bash
pnpm lint
pnpm typecheck
pnpm format:check
pnpm build
pnpm test
```

Other useful commands:

```bash
pnpm test:coverage
pnpm test:e2e
pnpm test:start-smoke
pnpm run check:repository-artifacts
```

`pnpm test` runs a production build and Bundle budget checks before Node contract tests. `pnpm test:e2e` uses real Chromium to verify key pages, identity, permissions, and error recovery.

### Business workflow tests with real dependencies

Prepare Docker Engine/Compose, Node/pnpm, and Python 3.12. Run `uv sync --frozen --extra test --extra structural` in `backend/`, then return to the repository root:

```bash
pnpm exec playwright install chromium
pnpm test:e2e:business
```

The command builds the current frontend, then creates a separate randomly named Compose project with loopback ports. It runs real PostgreSQL, Redis, MinIO, Neo4j, FastAPI, Dramatiq, outbox relay, and read-audit workers. Chromium requests pass through the Worker to verify approvals, permission denial, retries after network failures, idempotent replay, and five field-evidence uploads. Tests finally check database records and object hashes directly. On success or failure, the runner removes its own processes and synthetic data volumes; it does not operate on the saved local development stack.

Observations and reference material are synthetic. Diagnosis and embeddings use deterministic test implementations, and identity-provider, release, and image identities are test configurations. HTTP processes exercise the actual production authentication/storage protocol branches, while workers retain test model mode. These checks establish the engineering workflow, not model accuracy, a real identity provider, or production release acceptance. Reports and private logs are stored in `.artifacts/business-e2e/<run-id>/`; configuration, private keys, and traces may contain temporary credentials. CI uploads only `report.json`. The default browser suite and existing configuration-rotation smoke remain separate.

For direct browser uploads, configure the Worker's `WINDOPS_ARTIFACT_UPLOAD_ORIGINS` with the exact HTTPS origins of upload URLs issued by the backend, separated by commas, and allow PUT/CORS from the application origin in object storage. Default CSP permits only same-origin connections. The setting rejects wildcards, paths, credentials, and CSP directives; invalid values return 503 before executing business requests. Local HTTP is permitted only when both the page and storage use `http://127.0.0.1`, for the isolated tests above.

### Local user-performance measurement

First start the isolated stack using “Repeatable local startup on Windows”, then run from the repository root:

```powershell
./scripts/Start-Local.ps1
pnpm exec playwright install chromium
pnpm measure:performance --report .artifacts/improvements/performance.json
./scripts/Stop-Local.ps1
```

The measurement script connects only to loopback ports recorded in this repository's `.artifacts/local-stack/configuration.json`. It reads authentication from the isolated runtime configuration without printing credentials. It does not start or stop services or modify business data; real API read audits are still persisted. Use `--samples 10 --api-samples 40 --list-size 5000` to adjust sample counts and the size of synthetic load data. At least five browser samples and 20 API samples are required. Runs are sequential and retain every failed sample.

Reports distinguish three types of evidence:

- Chromium measurements at 1440px and 390px for the home page, diagnosis center, and predictive maintenance: FCP; time until the designated content is visible and two frames have elapsed; LCP, layout shifts, and long tasks up to that point; and latency from the global-search input event until results are visible and two frames have elapsed. Each sample uses a fresh browser context, while server and operating-system caches may already be warm. The 390px viewport is a narrow desktop-browser viewport, not a physical phone.
- Long alarm lists: 2,000 synthetic records following the actual Demo alarm structure are injected into a read response only within that browser run. The real page and DataTable perform refresh, pagination, and filtering. Demo queries have a 30-second cache; each sample waits 31 seconds of real time before triggering reconnection. This preparation is excluded from refresh-to-paint latency, and the browser clock is not modified. Reports retain the record count, response bytes, data digest, and actual DOM row count.
- An independent real FastAPI instance: authenticated requests to `/catalog`, `/turbines`, and `/data-catalog`, with one warm-up followed by measurements of complete response and JSON parsing time, P50/P95, returned counts, and response bytes. An empty database is explicitly recorded as returning zero rows. It does not establish throughput at production data scale or prove that the frontend-to-backend production path has passed acceptance.

Fixed local budgets are FCP 2,500ms, content readiness and list refresh 4,000ms, interaction 300ms, large-list filtering 1,000ms, and API P95 500ms. Missing samples, request failures, browser errors, or exceeded budgets save the report and exit nonzero. P95 uses nearest-rank and equals the maximum with five samples. Reports also record CPU/system/browser details, viewport, data volume, Git state, and build/script digests. Content readiness, the LCP cutoff, and interaction measured over two frames are local experimental metrics; they cannot stand in for real users' complete LCP, INP, or formal SLO acceptance.

### Python

From `backend/` with `backend/.venv` activated, run:

```powershell
python -m pytest tests -q
python -m ruff format --check src tests alembic scripts
python -m ruff check src tests alembic scripts
python -m mypy --no-incremental src
alembic upgrade head --sql
```

To verify optional CARE dependencies:

```powershell
uv sync --frozen --extra benchmark --extra test --extra dev
uv run windops-care-dependency-closure --requirements-lock requirements.container.txt --uv-lock uv.lock
uv run python -m pytest tests -q -k "care and not external_release"
```

SQLite tests use deterministic embeddings, an in-memory artifact verifier, and an in-memory graph substitute. They do not replace acceptance against PostgreSQL, TimescaleDB, MinIO, Neo4j, or real model providers.

Test counts come from command and CI discovery results. In ordinary local runs without external resources, `external_release` tests may be skipped; those skips do not count as release passes. Designated external acceptance environments must set `WINDOPS_FAIL_ON_SKIPPED=1`, making any skip a failure, and retain actual evidence according to the release acceptance checklist (local-only document: `docs/runbooks/release-acceptance.md`).

## Production acceptance boundaries

The production candidate includes delegated identity, RBAC, data scopes, idempotency, revisions, outbox, auditing, backup/restore, release identities, and fail-closed paths. The following still require completion in approved environments:

- Formal cluster deployment of the Python API and workers, image scanning, SBOM, signatures, and admission checks.
- Joint acceptance of PostgreSQL, TimescaleDB, Redis, MinIO, Neo4j, LiteLLM, and embedding services.
- Real SCADA, CMS, weather, and EAM data contracts and field permission integration.
- Disaster recovery, load tests, SLOs, alert routing, DAST, manual penetration testing, and post-release checks.
- Browser WCAG, visual regression, and supported-device acceptance.
- CARE license review, production object-storage replay, and manual review of ontology mappings across farms.

Cloudflare Sites hosts only the Web application and identity gateway; it does not host the Python backend. A successful Sites release does not replace acceptance of the backend, dependency stack, or field systems. Detailed evidence status is recorded in [EXECUTION_PROGRESS.md](./EXECUTION_PROGRESS.md), [AUDIT_REPORT.md](./AUDIT_REPORT.md), and [UI_AUDIT_REPORT.md](./UI_AUDIT_REPORT.md).

## Contributing

See the [contributing guide (Chinese)](./CONTRIBUTING.md) for development setup, validation requirements, and the PR process, and the [security policy (Chinese)](./SECURITY.md) for vulnerability reporting and credential protection.

Issues and Pull Requests are welcome for:

- Real problems in workflow completion, permissions, idempotency, or recovery.
- Accessibility, responsive layouts, data visualization, and runtime-state presentation.
- Capabilities with real data sources, a permission model, and acceptance criteria.
- Tests that reproduce issues and verify actual behavior.

Do not manufacture passing results by deleting failed tests, weakening assertions, returning hardcoded values, silently swallowing errors, or falling back to fixtures.

## License

OpenVigil's own source code is licensed under the [Apache License 2.0](./LICENSE).

The CARE v6 dataset and derived distribution artifacts subject to its license are not covered by Apache License 2.0 and are not distributed with this repository. Those assets follow [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), requiring source attribution, a license link, a description of changes, and ShareAlike.

## Acknowledgments

- [CARE v6](https://doi.org/10.5281/zenodo.15846963) — Christian Gück, Cyriana M. A. Roelofs / Fraunhofer IEE
- [EnergyFaultDetector](https://github.com/AEFDI/EnergyFaultDetector) — pinned official reference for CARE score verification
- PyScada, NetBird Dashboard, OpenClaw Mission Control, next-shadcn-dashboard-starter, and Grafana — references for information architecture, interaction, and visual research

See [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md) for complete third-party sources, pinned commits, licenses, and clean-room boundaries.
