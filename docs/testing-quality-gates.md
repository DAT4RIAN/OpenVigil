# Testing and quality gates

OpenVigil treats regression evidence as a release input rather than an optional report. Pull
requests and pushes to `main` run the same deterministic unit, contract, coverage, browser, and
bundle checks described here.

## Coverage budgets

Backend coverage is measured with branch data disabled and executable-line data enabled by
`pytest-cov`. CI rejects any of the following:

- global line coverage below 68%, the audited baseline;
- line coverage below 80% for access control, platform configuration, idempotency, or artifact
  storage, and below 90% for trusted identity or cryptographic security;
- regression below the approved measured floors for the audit's risk modules. The M-002
  transaction suite raises the weakest service floors to agent governance 52%, alarms 80%,
  operational views 55%, platform governance 58%, workflow 58%, and work orders 88%. The remaining
  measured floors are assets 38.5%, model registry 48%, SCADA 48.5%, knowledge graph storage 49%,
  dashboard 39%, and missions 45%;
- coverage below 65.5% for executable Python lines changed by the pull request or push. The full
  audited working-tree diff measured 65.83% (4,936 of 7,498 executable lines), so the gate is a
  real no-regression baseline rather than an aspirational value the current release cannot pass.

The raised service floors are backed by direct persistent-session failure injection plus a
non-skipping PostgreSQL contract for rollback, unique constraints, concurrent updates, idempotent
replay, side-effect failure, and tenant isolation. The changed-executable-line gate independently
prevents the measured working tree from sliding backward. It parses a zero-context Git diff and
intersects the resulting new line numbers with Coverage.py's executable-line inventory.
Documentation-only changes and deleted files therefore neither inflate nor weaken the result. The
budget checker itself has passing, failing, and floor-regression behavior tests.

Frontend tests use Node's native V8 coverage gate. CI requires at least 89% line, 49% branch, and
32% function coverage. The audited baseline on 2026-08-19 was 90.18%, 50.98%, and 33.33%,
respectively. The command has no skip list or coverage exclusion.

## Browser and PostgreSQL gates

The `browser-e2e` suite runs the built application in Chromium at desktop and 390-pixel mobile
viewports against the deterministic gateway fixture. Its production-mode scenarios verify trusted
identity and role capabilities, guarded navigation, the alarm-to-mission-to-approval-to-work-order
path, error and retry states, repeated click protection, keyboard access, and SSE resume behavior.

The separate `real-cross-layer-e2e` CI job is the release smoke and is never counted as the mock
browser suite: it starts the real FastAPI application against an isolated, migrated PostgreSQL
database, uses only narrow Redis/MinIO readiness doubles, routes through the Worker gateway, and
proves pending secret rotation -> delegated confirmation -> `/readyz` recovery. Its TLS, backend,
and Playwright evidence is uploaded under a separate artifact name. The release workflow requires
both same-commit checks through `backend/scripts/verify_release_checks.py`.

PostgreSQL migration, concurrency, prediction-lock, replay, idempotency, and critical-service
resilience contracts run in CI against a digest-pinned TimescaleDB image. The service resilience
suite proves work-order and approval rollback after late failures, first-revision uniqueness and
retry, alarm concurrency/idempotent replay, and operational-view tenant isolation. The job supplies
the required test URLs itself and sets `WINDOPS_FAIL_ON_SKIPPED=1`; a missing dependency or skipped
contract is a failure, not a manual follow-up.

## Standard production start gate

The frontend CI runs a fresh `pnpm build && pnpm test:start-smoke`. The smoke launches the documented
`pnpm start` command itself, waits for port 3000, and requests both `/` and `/api/runtime`. It requires
the default Demo responses to be 200, then restarts the same artifact with an explicit production
mode and no backend credentials and requires a structured fail-closed configuration error. The
runner terminates the complete process tree on Windows and POSIX and verifies the port is released.

## Client bundle budget

The production client build is limited to 2,700 KiB of JavaScript in total, 675 KiB for the
largest individual chunk, and one chunk above 500 KiB. The 2026-08-19 baseline was 2,558,782 bytes
across 91 chunks. The largest chunk was the route-isolated digital-twin page at 645,279 bytes; it
contains the Three.js turbine scene and ECharts operational overlays, while the Canvas renderer is
already emitted separately at 459,971 bytes. These approved ceilings leave only bounded build
variance and prevent another route from silently acquiring a comparable payload.

Run the local equivalents with:

```text
pnpm test:coverage
pnpm build && pnpm test:start-smoke
pnpm test:e2e
WINDOPS_E2E_REAL_BACKEND=1 pnpm test:e2e:real  # requires the isolated release-smoke backend
pnpm run check:bundle
cd backend
uv run pytest tests --cov=windops_backend --cov-report=json:coverage.json \
  --junitxml=backend-tests-junit.xml
uv run python scripts/check_coverage_budget.py --coverage-json coverage.json
```

## Formatting scope

`pnpm format:check` is the single frontend/document formatting command and
`uv run ruff format --check src tests alembic scripts` is the Python command. The root agent,
audit, execution-goal, and execution-progress records are authoritative control inputs rather than
source artifacts; `.prettierignore` explicitly excludes those four files so formatting cannot
silently rewrite their structure or operational state. All application, test, runbook, workflow,
and release documentation remains inside the gate.
