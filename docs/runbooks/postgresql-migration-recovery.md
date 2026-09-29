# PostgreSQL migration failure and retry

This runbook covers the production PostgreSQL 16, TimescaleDB, and pgvector migration job. The
supported upgrade window is `0015_alarm_command_state` through the repository's unique Alembic
head. Older databases must first follow a separately reviewed upgrade plan.

## Preconditions

- Take and verify a restorable PostgreSQL and object-store backup.
- Stop application writers and run exactly one migration job for the release commit and immutable
  image digest.
- Confirm the target database identity, current revision, PostgreSQL major version, TimescaleDB and
  pgvector availability, free disk, and the approved change window.
- Preserve the migration stdout/stderr, start/end timestamps, source revision, target revision,
  commit, image digest, and database identity as release evidence.

## Normal upgrade

Run `alembic current`, then `alembic upgrade head`, then `alembic current`. The final revision must
equal the single value printed by `alembic heads`. Verify the `scada_samples` hypertable, vector
column/HNSW index, declared constraints, representative row counts, and configuration-security
status before restarting writers.

## Failure response

1. Keep writers stopped and mark the migration gate failed. Do not run `alembic stamp`, edit the
   version table, or manually delete a failing object merely to advance the revision.
2. Capture the failing statement and PostgreSQL error without including credentials or row values.
   Run read-only `alembic current`, catalog, extension, lock, and storage checks.
3. Determine whether PostgreSQL rolled back the revision transaction. Compare both the
   `alembic_version` row and the columns/indexes/constraints introduced by the failed revision.
4. If the revision rolled back cleanly, remove only the independently created test/conflict object
   identified by the approved change, fix the migration in source, rerun CI from a clean database,
   and retry using a newly built immutable release artifact.
5. If any non-transactional extension or operation left partial state, do not retry blindly. Restore
   the verified pre-migration backup into a new isolated database, validate it, correct the
   migration, and repeat the full upgrade contract before changing the deployment target.

## Retry verification

The retry is successful only when all of the following hold:

- `alembic current` exactly equals the unique head and a second `alembic upgrade head` is a no-op.
- The empty-database and `0015_alarm_command_state -> head` jobs pass with representative data
  preserved.
- Extension versions, hypertable metadata, vector/HNSW behavior, constraints, and indexes match the
  contract test.
- PostgreSQL advisory-lock, mission transaction, Outbox atomic claim, and uniqueness concurrency
  tests pass with `WINDOPS_FAIL_ON_SKIPPED=1`.
- Configuration security remediation has no raw marker left and pending credential rotation remains
  a release-blocking condition.

The automated previous-revision test deliberately creates a conflicting migration object, proves
that the revision and new columns roll back, removes only that controlled object, and proves a clean
retry. A skipped PostgreSQL contract test is a failed gate.
