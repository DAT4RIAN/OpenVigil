# Bounded collection performance contract

OpenVigil list reads are page contracts, not implicit exports. The Sites Worker forwards exactly one
backend page and returns the backend cursor or offset metadata. It must never follow cursors on the
caller's behalf. A caller that needs more rows requests the next page explicitly. Raw full-ledger
export is not exposed by collection routes; governed handover/export uses a persisted report snapshot
and its digest-checked export route.

## Request budgets

- Diagnosis: `limit <= 64`, bounded `offset <= 10000`; primary and related rows are selected only for
  the requested page. Priority order is read as `critical -> high -> medium -> low` buckets, with
  `updated_at, id` ordering inside each bucket, so a computed global-risk sort is not required.
- Diagnosis summaries include only the latest Evidence row and latest AgentExecution row
  per Mission. The response metadata reports both limits and the number of Missions that were
  truncated. The complete ledgers remain available from the governed Mission APIs.
- Maintenance plans: `limit <= 50`, bounded `offset <= 10000`; tasks are loaded as total/completed
  aggregates rather than detail rows. Reservations/resources are limited to the latest row per
  Mission and resource type, and the metadata reports the number of truncated groups. Overlapping
  weather is restricted to the current work-order page.
- Resources and weather: independent stable cursors, each with `limit <= 100`.
- Turbine health history: `(recorded_at, id)` keyset cursor with `limit <= 100`.
- Health assessments: turbine cursor with `limit <= 100`; PostgreSQL performs an indexed lateral
  top-two health-event lookup per turbine and aggregates active alarms.
- Domain events: opaque scope-bound cursor and `limit <= 200`.
- A collection response must remain below 512 KiB at its maximum supported page size.

The release performance gate uses 100,000 Mission, WorkOrder, and AssetHealthEvent rows plus
pathological page fan-out: 24 Evidence and 24 AgentExecution rows per selected Mission, 80 Task rows
per selected WorkOrder, and six reservations for each of four resource types. It calls the real
FastAPI routes through the production services for default and filtered diagnosis/maintenance
requests. Each scenario runs a warm-up, 100 timed requests, and an isolated `tracemalloc` request.
P95/P99 use inclusive linear interpolation across those samples; JUnit also retains the absolute
maximum and the label/duration of the slowest SQL statement so isolated tails remain visible.

The gate fails if either diagnosis path executes more than 8 SQL statements, either maintenance
path executes more than 9, the count varies by row count, P95 is not below 500 ms, P99 is not below
1,000 ms, the Python peak reaches 64 MiB, or the final HTTP response reaches 512 KiB. It also patches
the shared query builders and requires the endpoints to invoke them, so an alternate unmeasured path
cannot silently replace the gated implementation. JUnit records, separately, page-plan execution
time, total database time, application/serialization time, end-to-end P95/P99, SQL count, Python
peak, and final HTTP bytes.

The 2026-08-20 isolated Windows/PostgreSQL reference run recorded:

| Scenario             | SQL |     DB P95 |    App P95 |        E2E P95 / P99 | Python peak | HTTP bytes |
| -------------------- | --: | ---------: | ---------: | -------------------: | ----------: | ---------: |
| diagnosis default    |   8 | 210.344 ms | 277.111 ms | 451.815 / 527.415 ms |   1,634,064 |    133,327 |
| diagnosis filtered   |   8 | 103.906 ms | 323.263 ms | 394.962 / 630.727 ms |   1,630,883 |    133,072 |
| maintenance default  |   9 | 116.814 ms | 134.485 ms | 276.785 / 482.891 ms |   1,537,783 |     86,800 |
| maintenance filtered |   9 | 152.975 ms | 126.126 ms | 293.052 / 474.880 ms |   1,632,525 |     86,801 |

`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` additionally verifies:

- bounded priority buckets ordered by stable Mission `updated_at, id` values and no disk sort;
- `ix_alarms_severity_id` for selective diagnosis priority branches;
- bounded work-order pages with no disk sort;
- filtered diagnosis/work-order plans retain their turbine indexes;
- `ix_asset_health_turbine_recorded_id` for per-turbine latest health events;
- the actual endpoint response, rather than ID rows, is the value used for byte and memory budgets.

Run the same non-skipping gate as CI against an isolated fixed-version PostgreSQL service:

```powershell
$env:WINDOPS_RUN_POSTGRES_CONTRACT_TESTS = "1"
$env:WINDOPS_FAIL_ON_SKIPPED = "1"
uv run pytest tests/external/test_postgres_migrations.py -m external_release -q `
  --junitxml=postgres-performance-junit.xml
```

## Knowledge graph projection budgets

Projection reads use server-side batches and atomically replace the derived graph only after a
complete build. The Outbox lease/retry path makes a failed or interrupted build recoverable while the
previous projection remains readable. Production defaults are 500 rows per batch, 250,000 source
rows, 250,000 nodes, 500,000 relationships, 256 MiB total projection memory, and 300 seconds runtime.
Every limit is configurable through the corresponding
`WINDOPS_KNOWLEDGE_GRAPH_PROJECTION_*` setting.

The memory limit is enforced in two independent ways. All graph entries and auxiliary indexes use a
recursive `getsizeof` accounting model with a 1.50 safety factor, while the projection also measures
its incremental Python allocation peak with `tracemalloc`. The measured Python peak must remain below
85% of the configured total, reserving 15% for allocator/native overhead. Snapshot validation,
sorting, tuple handoff, and the largest bounded Neo4j serialization batch are reserved before the
old graph can be replaced. Neo4j writes use the same configured batch size rather than materializing
all node and relationship payloads.

Mission and work-order lookups share compact context records instead of parallel full-size maps.
Resource reservations use two bounded database passes: the first derives resource scope, and the
second emits relationships after resource nodes exist. This removes the prior complete reservation
list from the live projection. Source-byte, graph-byte, measured/estimated peak-memory, row, and
runtime budgets remain independent; exceeding any one fails before replacement and leaves the
previous projection readable.

The production-shaped regression fixture builds 250 Missions with 1,000 Evidence rows, 750 Tasks,
500 Reservations, WorkOrders, KnowledgeCases, and Resources. Its current Windows reference run
recorded an 8,003,383-byte Python peak against a 33,554,432-byte configured ceiling. The same test
repeats a 128 KiB limit twice and requires both attempts to fail before atomic replacement. CI stores
the measured peak, configured ceiling, and primary entity count as JUnit suite properties.
