# OpenVigil Refactor Final Report

Status: `COMPLETE`  
Baseline: `e624bf7bc2042b65cd39c572b387ddb8c76252ad`  
Date: `2026-09-11` (`Asia/Shanghai`)

This report is the current-tree completion record required by `REFACTOR_PROMPT.md`. Historical audit or deployment text is not treated as evidence for this refactor.

## 1. Structural Outcome

| Area                   | Before                                                                   | After                                                                                                                  |
| ---------------------- | ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------- |
| Frontend imports       | 35 runtime consumers of the broad `lib/index.ts` fixture barrel          | Direct owner imports; `lib/index.ts` is a pure compatibility facade; 180/180 production modules reachable and 0 cycles |
| Page features          | Seven 1,200–1,472-line mixed data/state/view containers                  | Thin selectors plus feature-local contracts, hooks, support, views and drawers; route entrypoints unchanged            |
| CSS                    | One 8,287-line global file                                               | 18-line ordered entry plus 13 ownership modules; baseline token stream preserved                                       |
| Python graph           | 100 modules, 425 edges and one six-module CARE/service SCC               | 148 reachable source modules and 0 multi-module SCCs                                                                   |
| ORM and API schemas    | 1,551-line `models.py` and 1,109-line `schemas.py`                       | Ten ORM and seven schema owner modules; 142/155-line explicit compatibility facades                                    |
| CARE                   | Large modules mixed contracts, I/O, evaluation, prediction and execution | Neutral artifact utilities and bounded evaluation, import, runtime and prediction owners; public CLIs preserved        |
| Backend services       | Broad operational, catalog, model and metadata modules                   | Bounded query/command/serialization owners with 51–134-line compatibility facades                                      |
| Operation evidence I/O | Repeated streaming hashes and atomic JSON writers                        | One dependency-neutral implementation; each domain keeps its own schema, policy and errors                             |

No feature, route, migration, public compatibility namespace or security gate was intentionally removed. The work consists of ownership moves, exact helper consolidation, thin facades and executable topology/compatibility guards.

## 2. Split, Consolidated and Deliberately Retained

Split:

- Dashboard, Mission Detail, Data Center, Model Management, Alarm Center, Work Orders and Agent Control into feature-owned modules.
- Global styles into 13 ordered modules without selector/value redesign.
- SQLAlchemy models and Pydantic schemas by bounded context.
- CARE full-scale/import/evaluation/pipeline/scoring/anomaly responsibilities into owner modules.
- Operational views, Benchmark Catalog/metadata, model lifecycle and embedding providers into bounded owners.

Consolidated:

- Exact App-route JSON/no-store, record/string and bounded-integer primitives.
- Byte-equivalent CARE canonical JSON, SHA-256 and file-hash primitives.
- Byte-equivalent operation streaming SHA-256 and atomic report output.

Retained:

- `lib/index.ts`, `windops_backend.models`, `windops_backend.schemas` and historical service/CARE modules as explicit compatibility facades or cohesive orchestrators.
- `windops_backend`, `WINDOPS_*`, `x-windops-*`, route paths, console-script names, D1/Alembic history and all security/authorization boundaries.
- Domain-specific finite-JSON, path, status/error and hashing semantics where equivalence could not be proven.
- Large cohesive modules such as the Agent SQL tool catalog and Production domain adapter; static size alone was not used as deletion or extraction proof.

## 3. Compatibility Evidence

- Frontend surface: exact 22-page and 37 Worker/App-route signatures are locked by SHA-256 contracts.
- Backend surface: exact 95 `/api/v1` method/path signatures are locked (`653247...790d`); all 27 console-script targets import and are callable.
- Schema/ORM: 62 Pydantic JSON Schemas retain baseline hash `35c438...e6446f`; all 57 owned ORM declarations retain identity and the Alembic head/chain is unchanged.
- CSS/UI: the whitespace-insensitive pre-split rule stream is identical; fresh Chromium coverage includes desktop/tablet/mobile, 200% text, accessibility, keyboard, focus and reduced motion.
- Runtime semantics: facade identity tests, API/service tests and real PostgreSQL tests preserve errors, authorization, pagination, transaction, idempotency, revision, lease/fencing and rollback behavior.
- Demo/Production: Production failure remains fail-closed. No Production fixture, D1, WT-023 or simulated-event fallback was added.
- CARE: quality masks, truth isolation, content hashes, approved roots, model traceability, license and release gates remain enforced.

## 4. Final Validation Matrix

| Scope                                        | Result                   | Current-tree evidence                                                                                                             |
| -------------------------------------------- | ------------------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| `pnpm install --frozen-lockfile`             | PASS                     | Repository allows lifecycle scripts only for `esbuild`, `sharp` and `workerd`                                                     |
| typecheck / ESLint / Prettier                | PASS                     | No findings after final source changes                                                                                            |
| production build / bundle                    | PASS                     | 93 chunks, 2,612,302 bytes; largest chunk 645,029 bytes                                                                           |
| Node suite                                   | PASS                     | 178/178                                                                                                                           |
| Playwright Chromium                          | PASS                     | 29/29 against a fresh production build                                                                                            |
| `uv sync --frozen --all-extras --all-groups` | PASS                     | CPython 3.12 environment, 161 locked packages                                                                                     |
| Ruff / strict mypy                           | PASS                     | 268 formatted files; 148 source modules type-checked                                                                              |
| full Pytest discovery                        | PASS WITH EXTERNAL SKIPS | 419 passed, 28 skipped; skipped gates are classified below                                                                        |
| real PostgreSQL contract run                 | PASS                     | 23/23 migrations, 100k-row plans, concurrency, rollback, tenant scope and read-audit tests                                        |
| migrations / lock                            | PASS                     | Unique Alembic head `0028_read_audit_pipeline`, full offline render, `uv lock --check`                                            |
| CARE local gates                             | PASS                     | Dependency closure, official `v0.6.2` equivalence and clean-clone reference verification                                          |
| security                                     | PASS                     | Bandit and `pip-audit`; local package is correctly not resolved as a PyPI distribution                                            |
| local OCI image                              | PASS                     | Pinned bases, non-root `10001:10001`, hash-locked install, 20 entrypoints, `pip check`, CARE closure and PostgreSQL 16.14 clients |
| candidate repository tree                    | PASS                     | 644 blobs, each below the 10 MiB ceiling, 0 governed large artifacts; recursive gitlink clean clone succeeds                      |
| Markdown / diff / status                     | PASS                     | Local links, Prettier and `git diff --check` pass; final status is checked again after the completion record                      |

Evidence files under `backend/.artifacts/refactor/` are local ignored test outputs, not release attestations. The full backend JUnit record is `backend-full-junit.xml`; the explicitly enabled PostgreSQL record is `postgres-contract-junit.xml`.

## 5. Skipped, Unverified and Residual Risk

`SKIPPED` in the ordinary full Pytest run:

- 23 PostgreSQL-only cases were skipped in that generic run and then passed separately against an isolated migrated TimescaleDB/pgvector container.
- Four CARE PostgreSQL/full-scale cases require real external CARE artifact roots and stayed skipped.
- One external release-environment case requires explicit protected production services and credentials and stayed skipped.

`UNVERIFIED`:

- Real external CARE artifact import, full-scale evaluation and PostgreSQL vertical slice: required read-only artifact roots were not present.
- The real cross-layer protected production environment: no isolated provider endpoints/credentials were supplied.
- Registry-pushed immutable digest, generated SBOM/provenance, Trivy verdict, cosign signature and the full protected release gate: a successful local OCI build is not this evidence.

Residual risk is confined to those external gates. They are fail-closed and must run in their designated isolated environments before release qualification. No waiver converts them to `PASS`.

## 6. Completion Decision

The refactor is complete. RF-001 through RF-011 are implemented and verified, the full recheck and adversarial matrix passed, and two consecutive final audits found no new Critical/High issue. The externally gated CARE, protected cross-layer and registry-release scopes remain explicitly `UNVERIFIED`; this completion does not qualify or waive a production release.
