# Business-read audit pipeline

## Compliance contract

Every authorized business `GET` must be attributed before its handler queries
business data. The API appends one `windops.read-access.v2` event to the durable
Redis stream configured by `WINDOPS_READ_AUDIT_STREAM_KEY`. The event keeps the
server-owned subject, sorted roles, method, exact endpoint, UTC timestamp, query
parameter count, and SHA-256 fingerprints of the canonical query and access
scope. It never stores query values or the tenant, wind-farm, turbine, entity,
or data-scope lists themselves.

Redis admission is an atomic `XLEN` plus `XADD`. If Redis is unavailable or the
stream reaches `WINDOPS_READ_AUDIT_STREAM_MAX_PENDING`, the API returns `503`
with `READ_AUDIT_UNAVAILABLE` or `READ_AUDIT_BACKPRESSURE` and does not execute
the read. Do not bypass this gate during an incident.

## Batch writer and failure isolation

Run exactly the reviewed `windops-read-audit-worker` deployment. It uses a
consumer group, reclaims idle deliveries, writes at most
`WINDOPS_READ_AUDIT_BATCH_SIZE` events in one database transaction, and only
acknowledges/deletes stream entries after the transaction commits. Duplicate
delivery is harmless because `(accessed_at, id)` is the partition-compatible
primary key. A PostgreSQL outage therefore leaves events recoverable in Redis;
business reads continue until the explicit stream capacity is reached.

Alert on stream length, the oldest pending entry, worker restart loops, and any
API response with either read-audit error code. Restore PostgreSQL first, then
the worker. Never trim the stream manually. Capacity changes require a reviewed
estimate that covers the maximum outage window.

## Partition, archive, and retention policy

Alembic revision `0028_read_audit_pipeline` converts the live table to monthly
PostgreSQL range partitions and installs
`windops_ensure_read_audit_partitions(months_ahead)`. The checked-in daily
`windops-read-audit-maintenance` CronJob:

1. creates three future monthly partitions;
2. obtains the transaction-scoped PostgreSQL maintenance lock before selecting
   rows, so a manual start, retry, or second scheduler cannot archive the same
   batch concurrently;
3. selects no more than 10,000 hot rows older than 30 days;
4. serializes the complete minimized events as deterministic gzip JSONL;
5. inserts the SHA-256-addressed archive and deletes those live rows in the same
   transaction; and
6. deletes compressed archives only after 365 days from their last event.

The runtime validator requires the final retention to exceed the hot archive
age. Changing either period requires compliance approval and a migration/restore
exercise. Backups include both `read_access_audits` and
`read_access_audit_archives`; do not treat archive compression as a backup.

## Verification

After deployment, verify:

- a query containing a canary value does not persist that value, while its
  fingerprint changes when the query changes;
- 1,000 concurrent admissions stay within the accepted p95 threshold and
  require at most two 500-row database transactions after queueing;
- stopping PostgreSQL grows the stream without losing or acknowledging events;
- reaching the configured stream bound returns `READ_AUDIT_BACKPRESSURE`;
- restoring PostgreSQL drains the same event IDs without duplicates; and
- a maintenance run produces a gzip payload whose SHA-256 and row count match
  the archive record, then preserves it until its expiry.
