# OpenVigil Refactor Progress

本文件是本次代码重构的持久化执行状态。历史 `EXECUTION_PROGRESS.md` 只提供兼容背景，不覆盖本文件的当前状态。

## 1. Metadata

- Task source: `REFACTOR_PROMPT.md`
- Plan: `docs/refactor/REFACTOR_PLAN.md`
- Baseline HEAD: `e624bf7bc2042b65cd39c572b387ddb8c76252ad`
- Started: `2026-09-10` (`Asia/Shanghai`)
- Current phase: `COMPLETE`
- Current item: `COMPLETE`
- Final Audit Pass: `2 / 2`
- Final state: `COMPLETE`

## 2. Worktree Protection

- Initial user file: untracked `REFACTOR_PROMPT.md`.
- No reset, checkout, clean, commit or push is authorized.
- `pnpm install` generated an untracked invalid `pnpm-workspace.yaml`; it is part of RF-001 remediation, not user-authored baseline content.
- Project-local `backend/.venv` and dependency/build artifacts remain ignored implementation evidence, not source changes.

## 3. Status Register

| ID     | Status | Root cause                                                      | Primary risk                        | Evidence / next action                                            |
| ------ | ------ | --------------------------------------------------------------- | ----------------------------------- | ----------------------------------------------------------------- |
| RF-001 | DONE   | Missing valid repository-level pnpm lifecycle approval          | supply-chain expansion              | Exact allowlist and complete frontend gate set passed.            |
| RF-002 | DONE   | Broad `lib/index.ts` runtime fixture barrel                     | bundle and Demo/Production coupling | Zero app/component imports; facade and acyclic graph tests pass.  |
| RF-003 | DONE   | Repeated App-route protocol helpers                             | response/status drift               | Shared pure guards/parser/JSON response; 174 tests pass.          |
| RF-004 | DONE   | Largest page containers mix state/data/view                     | UI and state regression             | Seven bounded splits; full frontend and browser gates pass.       |
| RF-005 | DONE   | 8,287-line global stylesheet                                    | cascade/visual drift                | 13 ordered modules; baseline token-stream hash and UI gates pass. |
| RF-006 | DONE   | Six-module CARE/service Python cycle                            | import/type/CLI drift               | Neutral evaluation artifact contract; zero multi-module SCCs.     |
| RF-007 | DONE   | Monolithic models/schemas fan-in                                | ORM/migration/wire drift            | Bounded owner modules; ORM and JSON-schema compatibility locked.  |
| RF-008 | DONE   | CARE infrastructure duplication and giant orchestration modules | hash/truth/mask drift               | Shared artifact utilities and five bounded orchestration splits.  |
| RF-009 | DONE   | Broad backend services                                          | auth/query/transaction drift        | Bounded owners; facade identity and PostgreSQL regressions pass.  |
| RF-010 | DONE   | Repeated operation report I/O                                   | release evidence drift              | Shared exact primitives; 87 operation/release tests pass.         |
| RF-011 | DONE   | Topology/docs/final evidence not yet synchronized               | false completion                    | Topology gates, final report and two clean audits passed.         |

## 4. Baseline Evidence

### Repository and topology

- Initial Git status: `main...origin/main`, untracked `REFACTOR_PROMPT.md` only.
- TypeScript graph: 159 nodes / 672 edges / 0 cycles; `lib/index.ts` fan-in 35.
- Python graph: 100 nodes / 425 edges / one six-module CARE/service SCC.
- Routes: 22 pages, 37 Worker/App route modules, 95 FastAPI endpoints.
- Entrypoints: 27 Python console scripts; all declared targets exist.
- Migrations: 29 Alembic files with unique head `0028_read_audit_pipeline`; 7 Drizzle migrations.
- Hotspots and exact staged plan are recorded in `REFACTOR_PLAN.md`.

### Validation results

| Validation                                    | Status              | Result                                                                      |
| --------------------------------------------- | ------------------- | --------------------------------------------------------------------------- |
| `uv sync --frozen --all-extras --all-groups`  | PASS                | CPython 3.12.13 environment and 161 packages.                               |
| `uv run pytest`                               | PASS WITH SKIPS     | 397 passed, 28 skipped, 552.90 seconds.                                     |
| Ruff format/lint                              | PASS                | 212 files; no findings.                                                     |
| strict mypy                                   | PASS                | 100 source files; no findings.                                              |
| CARE dependency/CLI closure                   | PASS                | Locked package/import/CLI contract passed.                                  |
| Alembic head/declarations/offline render      | PASS                | `0028_read_audit_pipeline`; complete chain rendered.                        |
| `pnpm install --frozen-lockfile`              | INITIAL FAIL / PASS | RF-001 approved only esbuild, sharp and workerd; frozen install now passes. |
| build/bundle/typecheck/lint/format/Node tests | PASS                | 90 chunks / 2,617,797 bytes; 168/168 Node tests; all static gates pass.     |
| Playwright                                    | PASS                | 29/29 Chromium tests on a fresh production build in 1.7 minutes.            |
| real PostgreSQL/container/protected release   | UNVERIFIED          | Not rerun for this checkout during baseline.                                |

## 5. Execution Log

### Baseline investigation and plan drafted — 2026-09-10

- Fully read the controlling refactor prompt and project product, architecture, UI, audit, goal, progress, README and dependency/deployment configuration sources.
- Preserved the dirty/untracked worktree and distinguished historical completion from current evidence.
- Generated TypeScript and Python dependency graphs, CLI/API/migration/test inventories, hotspot list and duplicate-infrastructure candidates.
- Confirmed that current TypeScript production modules are acyclic and that Python has one CARE/service SCC.
- Ran current backend frozen dependency, test, format/lint, type, CARE closure and migration baselines.
- Reproduced the frontend pnpm ignored-build failure across install/build/type/lint/format/artifact commands.
- Created the phased plan before any business-code refactor.
- Validated both refactor control documents with Prettier and `git diff --check`.
- Started RF-001 after confirming pnpm `allowBuilds` semantics from official documentation.
- Added the exact `esbuild` / `sharp` / `workerd` lifecycle allowlist and a fail-closed policy contract test.
- Identified `format:check` as a Windows line-ending false failure (`index=LF`, `worktree=CRLF`, `core.autocrlf=true`); `endOfLine: auto` preserves all substantive Prettier checks without rewriting the worktree.

### RF-001 repository dependency-build policy — DONE — 2026-09-10

- Replaced pnpm's generated placeholder values with an exact fail-closed allowlist for `esbuild`, `sharp` and `workerd`; no wildcard or global lifecycle bypass is present.
- Added `tests/dependency-build-policy.test.mjs` to lock the reviewed policy.
- Added cross-platform `endOfLine: auto` after proving that Git's Windows LF-to-CRLF checkout, rather than substantive formatting, caused 279 false failures.
- Passed frozen install, production build, bundle budget (90 chunks, 2,617,797 bytes), typecheck, ESLint, Prettier, repository-artifact check and 168/168 Node tests.
- Passed 29/29 Playwright Chromium tests against a fresh production build in 1.7 minutes.
- Next: RF-002 replaces runtime imports from the broad `lib/index.ts` barrel in bounded batches and adds a topology regression gate.

### RF-002 frontend import ownership — DONE — 2026-09-10

- Moved lookup helpers to their owning Agent, farm, operations, knowledge and telemetry modules without changing normalization or return behavior.
- Moved the cross-domain fixture audit into `lib/domain-data-validation.ts`; retained `lib/index.ts` as a pure compatibility re-export facade.
- Replaced all 35 `@/lib` imports in application and component runtime modules with direct owning-module imports; no public route or component contract changed.
- Added `tests/import-boundaries.test.mjs` to reject broad runtime barrel imports, executable statements in the compatibility facade and TypeScript dependency cycles.
- Passed targeted selector/render/workflow tests (21/21), typecheck, ESLint, Prettier and `git diff --check`.
- Passed a fresh production build, bundle budget (93 chunks, 2,609,282 bytes) and the complete 171/171 Node suite, including Production fixture-fallback contracts.
- Next: RF-003 consolidates only response/status/query primitives whose current semantics are byte-for-byte compatible.

### RF-003 App-route protocol primitives — DONE — 2026-09-10

- Added shared JSON/no-store response, record/string guards and fail-closed decimal bounded-integer parsing to `app/api/_shared.ts`.
- Reused those pure primitives across Agent Tool, alarm, workflow, diagnosis, maintenance, predictive, catalog, knowledge-document and report routes while retaining each domain's existing status, error envelope, details and metadata.
- Kept SCADA's intentionally different numeric coercion and domain-specific error builders local rather than forcing unlike behavior into one abstraction.
- Added `tests/api-shared.test.mjs`; upgraded the catalog pagination test from a private-expression regex to both a shared-bound structural check and a real `limit=65` HTTP response assertion.
- The first full run exposed that stale implementation-detail assertion (173/174); after strengthening it, the full production build, bundle budget and 174/174 Node tests passed.
- Passed typecheck, ESLint, Prettier and targeted route suites (54/54 plus catalog/platform checks).
- Next: RF-004 splits the largest frontend feature containers one page at a time, beginning with Dashboard.

### RF-004A Dashboard container split — DONE — 2026-09-10

- Replaced the 1,206-line mixed Dashboard container with a thin runtime-mode entry and separate Demo, Production and shared incident-strip modules.
- Preserved the existing JSX, copy, query states and Demo/Production boundary; source-contract tests now read the owning child modules rather than relying on the old file layout.
- Passed typecheck, ESLint, 47/47 targeted contract/render/Production tests, fresh production build and bundle budget (93 chunks, 2,609,201 bytes).
- Passed 3/3 Dashboard Chromium layout/state tests at the existing acceptance viewports.
- Next: split Mission Detail along its generic-versus-featured workflow boundary.

### RF-004B Mission Detail container split — DONE — 2026-09-10

- Replaced the 1,362-line mixed Mission Detail container with a thin selector plus independent Generic Demo, featured WT-023 Demo, Production authority and shared formatting modules.
- Preserved runtime-mode routing, server-owned capabilities, idempotency keys, approval/work-order flow, comments and the generic read-only path; JSX bodies were moved without UI copy or DOM redesign.
- Passed typecheck, ESLint and 53/53 targeted identity/workflow/render/Production/lifetime-boundary tests.
- Passed a fresh production build, bundle budget (93 chunks, 2,609,201 bytes) and 7/7 identity/mobile Chromium tests.
- Next: split Data Center contracts/pure filtering from its stateful workspace.

### RF-004C Data Center container split — DONE — 2026-09-10

- Split the 1,472-line Data Center into explicit API contracts, pure catalog columns/formatters, a state/query/mutation hook and a view module.
- Preserved bounded Benchmark dataset/event/curve guards, truth isolation, Production data-source and contract mutations, query keys, stale states, CSV export and deep links.
- Updated source-contract tests to cover the complete feature module set; 22/22 targeted catalog/platform/table/Production-boundary tests passed.
- Passed typecheck, ESLint, fresh production build and bundle budget (93 chunks, 2,611,367 bytes).
- Passed 4/4 Chromium UI acceptance tests: all 22 routes, dashboard baselines, accessibility and Mission keyboard/reduced-motion checks.
- Next: split Model Management contracts and state/query orchestration from rendering.

### RF-004D Model Management container split — DONE — 2026-09-10

- Split the 1,221-line Model Management container into explicit API contracts, pure parsing/formatting support, a capability/query/mutation hook and a view module.
- Preserved model-artifact SHA-256 verification, upload/deploy/activate/rollback behavior, server-owned capability gating, query invalidation and the explicit CARE external-model lifetime warning.
- Updated the source-contract test to cover the complete feature module set; 20/20 targeted model/platform/Production-boundary tests passed.
- Passed typecheck, ESLint, fresh production build and bundle budget (93 chunks, 2,612,271 bytes).
- Passed 4/4 Chromium UI acceptance tests across all routes, visual baselines, accessibility and keyboard/reduced-motion behavior.
- Next: inspect and split the remaining Alarm, Work Order and Agent containers only at demonstrable state/data/view ownership boundaries.

### RF-004E Operational container splits — DONE — 2026-09-10

- Split Alarm Center, Work Orders and Agent Control into their list workspaces, bounded detail/command drawers and feature-local contract/support modules; no resulting feature module exceeds 800 lines.
- Preserved alarm acknowledgement/assignment and authoritative detail queries, work-order artifact SHA-256/upload/task completion, Agent read-only tool preview/runtime commands/releases, Demo workflow overlays and Production event cursor behavior.
- Source-contract tests now follow the owning feature modules rather than assuming all behavior remains in the route container; assertions and user-visible contracts were not weakened.
- Passed typecheck, ESLint, the acyclic import gate, targeted table/Production/event/Agent contracts, a fresh production build and bundle budget (93 chunks, 2,612,302 bytes).
- Passed the complete 174/174 Node suite and 29/29 Chromium suite (all state matrices, 22 routes, desktop/tablet/mobile, 200% text, visual baselines, accessibility, keyboard and Production identity/capability behavior).
- Next: RF-005 moves contiguous CSS ownership groups without changing selector order or values.

### RF-005 Ordered CSS module split — DONE — 2026-09-10

- Replaced the 8,287-line `app/globals.css` with a thin Tailwind/source/import entry and 13 numerically ordered ownership modules covering foundations, shell/shared UI and bounded page families.
- The first long-file transfer was detected as truncated before validation; every module was rebuilt from the unchanged baseline Git blob in bounded ranges, and the reconstructed raw rule stream matched the pre-split SHA-256 exactly before formatting.
- Prettier changed whitespace only at standalone-file boundaries; the whitespace-insensitive token stream remains byte-identical to the baseline and is locked by `tests/css-module-boundaries.test.mjs` together with the exact ordered import list.
- Updated responsive and typography source contracts to traverse the physical CSS modules; no assertions were removed or relaxed.
- Passed CSS/Prettier checks, 7/7 CSS/responsive/typography contracts, production build and bundle budget (93 chunks, 2,612,302 bytes).
- Passed 10/10 Chromium viewport/typography/visual/accessibility/keyboard tests covering 1440, 1280, 900, 390 and 200% text cases.
- Next: RF-006 breaks the measured six-module Python CARE/service SCC by moving dependency-neutral contracts first and retaining stable re-exports.

### RF-006 Python CARE/service cycle removal — DONE — 2026-09-10

- Traced the six-module SCC to the anomaly runtime's lazy reverse import of the full offline evaluator; the remaining schema/metadata/model edges were one-way once that edge was removed.
- Moved the evaluation-suite version/protocol constants, error type, immutable specification, canonical artifact builder and verifier into dependency-neutral `evaluation_artifact.py`.
- Kept the historical `windops_backend.benchmarks.care.evaluation` names as explicit same-object re-exports; anomaly and evaluation now both depend one-way on the neutral contract.
- Added `backend/tests/test_import_boundaries.py`, which builds the full package AST import graph and rejects every multi-module strongly connected component.
- Passed 127/127 CARE/model/import-boundary tests, all 27 declared console-entrypoint imports, Ruff format/lint, and strict mypy across 101 source files.
- Next: RF-007 separates ORM models and Pydantic schemas by bounded context while preserving the original module facades and declaration identity.

### RF-007 ORM and Pydantic bounded-context split — DONE — 2026-09-10

- Moved the shared SQLAlchemy base/constants to `model_base.py`, 57 ORM declarations into 10 ordered bounded-owner modules, and 62 Pydantic models plus seven public constants/type aliases into seven schema-owner modules.
- Retained `models.py` and `schemas.py` as explicit `__all__` compatibility facades; every public class resolves to the exact owner-module object.
- Proved all 57 ORM class declaration token streams equal to baseline before locking the split; current metadata registers all 57 owned tables even when optional test modules add their own tables.
- Compared all 62 generated Pydantic JSON Schemas against an isolated execution of the baseline Git source: the canonical SHA-256 is identical (`35c438...e6446f`).
- Added model/schema façade, identity, ownership, table-count and JSON-schema regression tests. The first combined run found that the test assumed no optional tables could share the registry; it was corrected to assert the exact owned table set, while the other 64 compatibility/API tests passed.
- Passed the corrected boundary/import suite (5/5), Ruff across source/tests, strict mypy across 119 source files, Alembic unique head `0028_read_audit_pipeline`, and the complete offline migration render.
- Next: RF-008 consolidates only proven-identical CARE artifact primitives and separates CARE orchestration in bounded batches.

### RF-008 CARE artifact and orchestration boundaries — DONE — 2026-09-10

- Consolidated the proven-identical permissive canonical-JSON/SHA-256 implementation used by anomaly, contract, importer, pipeline, quality, replay and trust, plus the identical importer/pipeline file hasher, in `artifact_utils.py`.
- Deliberately kept finite-JSON implementations with domain-specific exception types/messages separate in Scoring, Full-scale and offline evaluation.
- Split offline evaluation artifacts, Full-scale import and evaluation, Pipeline runtime/storage/job control, Scoring protocol/prediction, and Anomaly runtime contracts into independent owner modules; legacy modules re-export the same class/function objects and CLI entrypoints.
- Added shared-utility golden/non-finite/chunk tests and legacy-to-owner identity tests; the one new-test failure required only removing an assertion for an intentionally eliminated unused private alias.
- Passed zero-SCC import checks after replacing package-level imports with direct module imports, all 27 console-entrypoint imports, Ruff across 200 files and strict mypy across 125 source files.
- Passed the complete 131/131 CARE/model/import-boundary non-external suite in 303.26 seconds. Real external source/PostgreSQL/full-scale execution remains outside this evidence and is still `UNVERIFIED` pending final environment checks.
- Next: RF-009 splits broad backend read/service modules one at a time without moving command transaction boundaries.

### RF-009 Broad backend service boundaries — DONE — 2026-09-11

- Split `operational_views.py` into shared query contracts, bounded related-data loaders, diagnosis, maintenance and asset/report/catalog owners; the legacy module is a 134-line compatibility facade. Public query builders and constants remain available, while the two high-level page functions retain their original signatures and old-module query-builder injection behavior.
- Split Benchmark Catalog into policy, dataset, event, replay and evaluation/diagnosis read owners; `benchmark_catalog.py` is now a 64-line explicit same-object facade.
- Split model services into runtime contracts, registration/deployment, activation governance, inference and pure serialization owners. Registration, deployment and activation transaction bodies moved intact; the process-local prediction-lock registry remains singular.
- Moved embedding provider protocols, provider calls, chunking and vector primitives to dependency-neutral `agents/embeddings.py`; SQL tool orchestration stays in `agents/tools.py`, and knowledge ingestion now imports the owner directly.
- Split Benchmark metadata into shared identity locking plus registration, evaluation, replay, anomaly-policy and trace owners. Every command transaction function moved as a whole and remains an exact facade export.
- Added `test_service_module_boundaries.py` to lock public owner identity and bounded facade/owner sizes. Updated one Production RAG source contract to follow the provider implementation to its new owner without changing its pgvector or fail-closed assertions.
- Passed Ruff across all source, strict mypy across 147 source files, the zero-SCC import gate and 67/67 targeted service/API/runtime tests covering query-count limits, authorization, model activation/inference, embeddings, metadata idempotency and facade ownership.
- PostgreSQL-only concurrency and vertical-slice tests remain pending the final environment gate rather than being inferred from SQLite evidence.
- Next: RF-010 consolidates only byte-equivalent operation-report file hashing and atomic JSON output primitives.

### RF-010 Operation report I/O primitives — DONE — 2026-09-11

- Added dependency-neutral `operations/report_io.py` with the shared 1 MiB streaming SHA-256 implementation and durable, newline-stable, sorted atomic JSON replacement primitive.
- Reused the hash implementation from backup, release-gate, deployment-policy, CARE full-scale acceptance and CARE execution-plane code while preserving every historical callable name as the same function object. The small CARE PostgreSQL `read_bytes()` hasher remains separate because its memory behavior is not identical.
- Reused atomic JSON output from release evidence, release smoke, container verification, deployment policy, CARE PostgreSQL evidence, CARE execution-plane evidence and release qualification. Each caller still owns its exception type/message, overwrite policy, evidence schema and gate logic; deployment policy retains its `.tmp` suffix behavior.
- Added `test_operation_report_io.py` covering golden bytes, chunked hashes, exact facade identity, replacement, temporary cleanup, fail-closed symlink behavior and a source gate rejecting duplicate `mkstemp`/`json.dump` implementations in operation modules.
- Passed Ruff and strict mypy across all 12 operation modules and 87/87 release, deployment, container, backup/DR, CARE evidence and shared-I/O tests, including negative suites.
- Next: RF-011 updates the architecture map, adds final orphan/entrypoint checks and converges the full validation matrix.

### RF-011 Topology, documentation and final convergence — DONE — 2026-09-11

- Updated `ARCHITECTURE.md` and the README directory map for feature-owned frontend modules, ordered styles, bounded backend owners and compatibility facades.
- Extended the TypeScript boundary gate to reject cycles and unreachable production modules while locking 22 page and 37 Worker/App route entries; all 180 current production modules are reachable from explicit runtime/build roots.
- Extended the Python boundary gate to reject cycles and unreachable modules while importing all 27 console scripts; all 148 source modules are reachable from FastAPI, CLI or the explicit public online-CARE root.
- Added an exact 95-route `/api/v1` signature contract and a repository-wide local Markdown-link check. Reviewed all declared production dependencies against owner imports or the vinext/React framework runtime contract; none are unowned.
- Final frontend evidence: frozen install, typecheck, ESLint, Prettier, production build, bundle budget (93 chunks / 2,612,302 bytes), 178/178 Node tests and 29/29 Playwright Chromium tests passed.
- Final backend evidence: frozen sync (161 packages), Ruff, strict mypy (148 files), 419 passed / 28 externally gated skips, and 23/23 separately enabled real PostgreSQL/TimescaleDB/pgvector tests passed.
- Alembic has the unique head `0028_read_audit_pipeline`; the complete offline chain, lock check, CARE dependency closure, official reference equivalence, Bandit and `pip-audit` passed.
- Built `openvigil-refactor:local` from pinned bases and verified non-root UID/GID, hash-locked dependencies, all 20 required runtime entrypoints, `pip check`, CARE closure and PostgreSQL 16.14 clients. Registry publication, SBOM/Trivy/cosign and protected-release credentials remain `UNVERIFIED` rather than local-build `PASS`.
- Repaired candidate-tree CARE reproducibility without touching the user index: the first pre-report candidate records mode `160000` at commit `a338b6ef...2f63e`; its 642 blobs / 20,594,192 bytes pass artifact policy, a recursive clean clone checks out tag `v0.6.2`, and the official equivalence gate passes there.
- Four real CARE artifact/PostgreSQL tests, the real cross-layer protected environment and the protected registry release remain `UNVERIFIED` because no isolated external CARE artifacts or release credentials/endpoints are available. Their skips are not counted as passes.
- Added `REFACTOR_FINAL_REPORT.md` and `REFACTOR_AUDIT.md`; the adversarial review and two consecutive final audits found no new Critical/High issue.
- Rebuilt the complete 644-blob candidate tree after the audit records, recursively cloned its fixed CARE gitlink, and reran the official reference equivalence gate from the clean clone.

## 6. Completion Gates

| Gate                                                  | Status  |
| ----------------------------------------------------- | ------- |
| All planned items implemented and verified            | PASS    |
| Public routes/API/errors/permissions/data unchanged   | PASS    |
| No Production fixture fallback                        | PASS    |
| No new cycles, orphans or duplicate infrastructure    | PASS    |
| Documentation matches final structure                 | PASS    |
| Full regression or explicit UNVERIFIED evidence       | PASS    |
| Full recheck and adversarial review                   | PASS    |
| Two consecutive audits with no new Critical/High      | `2 / 2` |
| Progress matches Git status                           | PASS    |
| Final structural/compatibility/validation/risk report | PASS    |
