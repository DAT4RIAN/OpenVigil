# CARE v6 full-scale operations

## Scope and hard boundaries

This runbook covers the bounded A → C → B import and within-farm evaluation of
CARE v6. The source directory and ZIP are read-only. Full signal data stays in
wide Parquet; the full dataset must never be expanded into TimescaleDB. Only
approved Avg features are model inputs, although every mapped source signal is
preserved in the governed standard artifact. Prediction truth is opened only by
the final evaluator after the prediction-freeze manifest has been published.

Cross-farm claims remain disabled. Enabling them requires a versioned ontology,
named human review records, and a separately approved protocol. Anonymous sensor
numbers must not be aligned across farms by name alone.

The import/evaluation worker requires `benchmark`. Artifact export additionally
requires `model` and `benchmark_export`; truth requires the separate
`benchmark_truth` scope. The API, browser, and import worker receive no cleanup
permission. Raw CARE objects are never cleanup eligible. See
`care-artifact-governance.md` for distribution and exact-scope cleanup rules.

## Frozen acceptance and resource policy

The release run must close exactly 95 events in A22 → C58 → B15 order, 36
farm-namespaced assets, 45 anomaly events, 50 normal events, 5,242,948 rows, and
281,249 prediction points. A partial or reordered run is invalid.

The `care-v6-full-scale-resource-policy-v5` defaults are release gates, not
advisory targets:

| Boundary              |               Limit |
| --------------------- | ------------------: |
| Import wall time      |            43,200 s |
| Evaluation wall time  |            21,600 s |
| Record batch          |              16 MiB |
| CSV read block        |               1 MiB |
| Arrow allocation      |             512 MiB |
| Process resident HWM  |               1 GiB |
| Import artifacts      |              64 GiB |
| Evaluation artifacts  |               8 GiB |
| Import throughput     | at least 100 rows/s |
| Prediction points     |     at most 281,249 |
| Parquet row group     |          8,192 rows |
| Replay batch          |          1,000 rows |
| Replay write rate     |  at least 50 rows/s |
| Catalog page          |           64 events |
| Curve response        |          512 points |
| Frontend API response |             512 KiB |
| Governed query p95    |              500 ms |

A resource violation is a terminal failed run. Do not make the limit larger to
turn a failed candidate into a pass. Diagnose the host, storage, or query first;
changing the policy requires a reviewed new policy version and a fresh run.
Registration and independent verification supply the pre-registered policy to
the verifier; the manifest cannot authorize a larger limit for itself. The
verifier recomputes import resource totals from immutable event references,
recomputes evaluation storage and batch/Arrow peaks, checks the actual wall
clock, and resolves every prediction reference before accepting the run.
The memory gate uses the operating system's whole-process resident high-water
mark, so Python, Arrow, and other native allocations are all included without
the runtime distortion of per-allocation tracing. Between bounded Parquet,
quality, training, and prediction phases, the worker returns unused allocator
pages to the operating system; failure to perform that trim fails closed.
CSV checkpoints remain small and restartable, while the final Parquet merge
coalesces them into exact 8,192-row groups (except the final remainder). This
prevents per-fragment Parquet metadata from growing with the number of CSV read
blocks; the physical row-group count is verified before publication and replay.

The PostgreSQL release performance contract uses fixed work rather than an
operator-selected sample. Replay measures seven API transactions of 54 samples
each and requires at least 50 rows/s. Its JUnit profile must contain exactly
seven database measurements, no more than 40 SQL statements per transaction,
and a consistent database-time aggregate. The PostgreSQL fast path performs one
receipt upsert, one ordered stream-state lock and one flush for an all-accepted
batch. Receipt conflicts, quarantine candidates, repeated source event IDs and
direct alarm-producing samples fall back to the fully general per-sample path;
the optimization must not weaken idempotency, ordering or alert side effects.

Catalog validation registers all 95 events and 36 evaluation runs, warms five
governed page requests once, then measures each request 20 times. Every request
must stay at or below 12 SQL statements, every endpoint p95 must stay at or below
500 ms, and every response must stay at or below 512 KiB. The evidence verifier
rejects missing, non-finite, inconsistent or over-budget SQL profiles in addition
to the existing end-to-end thresholds.

## Preflight

Run from the repository root. Confirm the control manifest and quality contract
exist, the source hashes still match, the CARE bucket is private/versioned, and
the worker identity has no `DeleteObject` permission. Do not place the output
inside the source directory.

Production workers must select `--use-care-worker-runtime`. This reads only the
dedicated `WINDOPS_CARE_DATABASE_URL` and `WINDOPS_CARE_MINIO_*` values from the
external `windops-care-runtime` Secret. Startup requires PostgreSQL TLS, MinIO
TLS, a strong dedicated secret, and an explicit denial list containing all four
operational buckets. `--use-configured-minio` remains a compatibility path for
the general runtime, and `--object-store-root` is the mutually exclusive
filesystem adapter for isolated local validation; neither is the approved
production batch path.

The normal worker deliberately has no `DeleteObject` permission. It uploads to
the private `care/v6/_tmp/` prefix, copies and verifies the content-addressed
final object, and attempts best-effort removal of the temporary object. An
`AccessDenied` from that cleanup is expected only after the final size and SHA
have been verified; the temporary object remains non-release evidence and the
mandatory seven-day `_tmp` lifecycle removes it. Any other cleanup failure, or
any failure before final-object verification, remains retryable and fail-closed.

```powershell
Push-Location backend
uv lock --check
uv run windops-care-dependency-closure `
  --requirements-lock requirements.container.txt `
  --uv-lock uv.lock `
  --report ..\.artifacts\care-v6\preflight\dependency-closure-<change-id>.json
uv run windops-care-contract `
  --dataset-root C:\coding\reference\CARE_To_Compare `
  --zip-path C:\coding\reference\CARE_To_Compare.zip `
  --output ..\.artifacts\care-v6\preflight\manifest-<change-id>.json
$approvedHash = (Get-Content -Raw ..\.artifacts\care-v6\contract\manifest.json |
  ConvertFrom-Json).manifest_sha256
$candidateHash = (Get-Content -Raw ..\.artifacts\care-v6\preflight\manifest-<change-id>.json |
  ConvertFrom-Json).manifest_sha256
if ($approvedHash -ne $candidateHash) { throw "CARE source contract drift" }
Pop-Location
```

Never overwrite the approved manifest or modify the source to resolve a
mismatch.

The dependency-closure report is mandatory release evidence. It records the
exact `uv.lock` and production container-lock SHA-256 values, verifies the six
benchmark runtime distributions against those locks, imports all CARE modules,
and runs all CARE CLI help paths. A missing package, entrypoint, or mismatched
version fails closed before source data is opened.

## Import and evaluation

Use unique, traceable job IDs. A local object-store root is suitable only for
local acceptance; production uses the private CARE MinIO bucket through the
worker adapter.

```powershell
Push-Location backend
uv run windops-care-full-scale import `
  --manifest ..\.artifacts\care-v6\contract\manifest.json `
  --quality-contract ..\.artifacts\care-v6\quality\quality-contract.json `
  --dataset-root C:\coding\reference\CARE_To_Compare `
  --archive C:\coding\reference\CARE_To_Compare.zip `
  --output-root ..\.artifacts\care-v6\full-scale `
  --object-store-root ..\.artifacts\care-v6\full-scale-object-store `
  --job-id care-v6-full-import-<change-id>

uv run windops-care-full-scale evaluate `
  --import-manifest ..\.artifacts\care-v6\full-scale\care\v6\reports\full-import\manifest.json `
  --output-root ..\.artifacts\care-v6\full-scale `
  --object-store-root ..\.artifacts\care-v6\full-scale-object-store `
  --job-id care-v6-full-evaluation-<change-id>

$env:WINDOPS_DATABASE_URL='<approved PostgreSQL async URL>'
uv run windops-care-full-scale register `
  --source-manifest ..\.artifacts\care-v6\contract\manifest.json `
  --quality-contract ..\.artifacts\care-v6\quality\quality-contract.json `
  --import-manifest ..\.artifacts\care-v6\full-scale\care\v6\reports\full-import\manifest.json `
  --evaluation-manifest ..\.artifacts\care-v6\full-scale\care\v6\reports\full-evaluation\manifest.json `
  --artifact-root ..\.artifacts\care-v6\full-scale `
  --tenant-id tenant-east-china `
  --subject care-full-scale-worker
Pop-Location
```

For the equivalent production worker invocation, replace the
`--object-store-root ...` line with `--use-care-worker-runtime` after the CARE
bucket versioning/lifecycle/worker policy preflight has passed. Registration
also receives `--use-care-worker-runtime` so it uses the dedicated, TLS-only
PostgreSQL registration role rather than the API configuration.

## Kubernetes execution plane and release evidence

The `windops-care-full-scale` CronJob is a suspended execution template, not a
recurring benchmark schedule. It selects the isolated `care-v6-offline` queue,
one concurrent pod, three total attempts (`backoffLimit: 2`), and a 72,000-second
deadline. Its source PVC is mounted read-only; checkpoints, derived artifacts,
and replay results use the separate encrypted workspace PVC. The pod has a
dedicated ServiceAccount and Secret and can reach only DNS, the labelled CARE
PostgreSQL service, and the labelled CARE MinIO service.

After source approval and release-manifest rendering, create one traceable Job:

```text
kubectl create job care-v6-<release-id> \
  --from=cronjob/windops-care-full-scale \
  --namespace windops
```

The command runs dependency closure, import, evaluation, and transactional
registration, then repeats all three operations with the same immutable output
and state paths. The second import/evaluation must report `replayed=true`; the
second registration must replay existing rows without duplication. Kubernetes
retries reuse the same workspace and job identity, while the application state
still refuses a fourth attempt.

The independent release runner packages
`artifacts/care/care-full-scale-release-evidence.json` plus exactly ten named
roles under `artifacts/care/fullscale/`: dependency closure, import/evaluation
manifests, import/evaluation states, import/evaluation replay results, initial
and replay registration results, and storage-scope proof. Every artifact entry
includes its role, relative path, SHA-256, and media type.
`windops-care-fullscale-acceptance` parses these raw artifacts and rejects identity
drift, fewer than 95 events or 36 folds, enabled cross-farm claims, failed
resource limits, incomplete replay/registration, writable source, storage
policy drift, or access to any operational bucket. The protected release
workflow additionally runs `windops-care-workload-smoke` from the exact built
image and will not qualify the release unless both CARE checks pass.

Success is the final JSON line with a manifest path and SHA-256, followed by an
independent rerun that returns `replayed=true` and the same file SHA-256. Verify
the import and evaluation manifests both report `limits_passed=true`; the
evaluation must contain 36 farm-namespaced folds, account for all 95 events, and
keep `cross_farm_protocol.status=disabled`.
Database registration is one transaction across both verified manifests. A
database outage rolls it back; after recovery, rerun the same command and
require every previously created row to be reported as replayed rather than
duplicated.

## Observe, cancel, and resume

State documents are hash-protected and live under `<output-root>/.state/` unless
an explicit `--state-path` was supplied. Inspecting or cancelling a corrupt state
fails closed.

```powershell
Push-Location backend
uv run windops-care-full-scale status `
  --state-path ..\.artifacts\care-v6\full-scale\.state\<job-id>.json

uv run windops-care-full-scale cancel `
  --state-path ..\.artifacts\care-v6\full-scale\.state\<job-id>.json
Pop-Location
```

Cancellation becomes durable after the current event boundary. Wait for
`status=cancelled`; do not kill the process while it is publishing an immutable
object unless the host itself is failing. Resume a cancelled or terminal failed
run with a new job ID. The new run reuses only fully verified event summaries and
content-addressed objects. A retryable outage leaves `status=pending`; retry the
same job ID while its attempt count is below three. A completed aggregate
manifest is immutable and any job ID replays it.

`running` with a stale heartbeat means the worker disappeared. Confirm no worker
with that exact job ID is alive before retrying; two writers for one state file
are not an approved recovery method. Preserve the state and logs as incident
evidence.

## Fault response

- **Object store unavailable:** keep the task failed closed, restore the CARE
  bucket endpoint and credentials, confirm no unverified final object exists,
  then retry the pending job. A private `care/v6/_tmp/*.partial` object may
  remain when the no-delete worker reaches the expected lifecycle-deferred
  cleanup boundary; verify the seven-day lifecycle and never treat that object
  as release evidence. Never redirect CARE artifacts to a production-data
  bucket.
- **Database unavailable:** import/evaluation files may finish independently,
  but metadata registration remains incomplete and the release is blocked.
  Restore PostgreSQL, verify the unique Alembic head, then replay idempotent
  registration. Do not mark filesystem success as database completion.
- **Hash/schema corruption:** quarantine the derived artifact, retain its object
  key and audit evidence, and rebuild from the immutable source. Do not edit the
  JSON hash or Parquet metadata in place.
- **Resource violation:** preserve the terminal state and telemetry. A new run is
  allowed only after the capacity or implementation cause is corrected.
- **Partial result:** absence of either aggregate manifest means the phase is not
  complete. Event checkpoints are recovery inputs, never release evidence by
  themselves.

## Backup and isolated recovery

The CARE bucket is part of the authoritative backup set. Run backup during a
change freeze (or record the versioned-object freeze interval) and require the
manifest plus its SHA-256 sidecar. Test recovery only into an isolated database
and non-overlapping buckets.

```powershell
Push-Location backend
uv run windops-backup --output-dir <approved-backup-root>
uv run windops-dr-drill `
  --output-dir <approved-dr-evidence-root> `
  --confirm-target <isolated-database-name>
Pop-Location
```

Recovery is accepted only after every object is read back and hash-verified,
Alembic/current and row-count invariants pass, the CARE bucket is present in the
manifest, and the generated DR evidence records RTO and recovery point. Never
use `--allow-object-overwrite` outside an explicitly approved in-place recovery.
The complete recovery procedure and target environment variables are in
`backup-recovery.md`.

## Release evidence

Retain the two immutable aggregate manifests and their object-store copies, job
states, resource measurements, database registration counts, bounded API/query
measurements, backup/DR evidence, license verification, and final global gate
outputs. Candidate release stays blocked if any event is failed/unscorable but
unaccounted, any truth-freeze or license verification fails, a frontend/JSON
value is needed to bypass the server gate, or either final audit has not passed.

## Validated release candidate (2026-08-27)

The locally validated candidate is `care-m004-final-20260827`, built from commit
identity `e70788b8fe040603fb3be718568db9da44eacbb1`. Its local immutable image
content ID is
`sha256:d497a1ab2fbbee4dae2a6ed6197b1ef3abf73b0a0f3ccbdcbc0f79781c122a84`.
This content ID is local evidence only; it is not a substitute for the registry
digest, signature, attestation, SBOM, cluster dry-run, or protected production
admission evidence.

The accepted full import ran in the required A22 → C58 → B15 order and closed
95 events, 36 farm-namespaced assets, 45 anomaly events, 50 normal events,
5,242,948 rows, and 281,249 prediction points. Import wall time was 7,846.499
seconds at 693.519 rows/second with a 521,977,856-byte process high-water mark.
The within-farm evaluation covered all 36 leave-one-asset-out folds and all 95
events in 125.829 seconds with a 235,524,096-byte process high-water mark. It
recorded 12 passing and 24 failing model candidates; failing candidates remain
accounted for and are not releaseable. Cross-farm evaluation remains disabled
because no approved ontology or human review record exists.

Fresh PostgreSQL validation registered the complete import and evaluation
twice without duplication, kept all full-signal TimescaleDB row counts at zero,
and bounded the governed API to a 330.274 ms maximum observed p95 and a 127,879
byte maximum response. The isolated platform replay wrote 378 samples at 60.772
rows/second, persisted seven predictions, produced one traceable
Alarm/Mission/Decision chain for the anomaly event, and produced no alarm for
the normal event. Restart, same-run replay, new-run isolation, truth access,
governed export, and ShareAlike review all passed.

The isolated disaster-recovery drill restored PostgreSQL schema revision
`0028_read_audit_pipeline`, all governed table invariants, and all required
CARE MinIO objects with exact size and SHA-256 metadata. Its measured recovery
time objective was 1,387.397 seconds. Source and recovery identities had no
delete permission, and lifecycle-managed `_tmp` objects were excluded from the
backup and recovery evidence.

The candidate passed the current local build, formatting, lint, type checking,
unit/integration/PostgreSQL tests, Chromium E2E, startup smoke, image runtime,
image release smoke, migration checks, dependency audits, Bandit scan, and
rendered Kubernetes policy checks. Promotion remains fail-closed until the
protected release system supplies the registry digest and its required signing,
attestation, SBOM, cluster validation, and admission results.
