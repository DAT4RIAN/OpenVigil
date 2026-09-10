# ADR 0001: CARE v6 columnar pipeline and execution boundary

- Status: Accepted
- Date: 2026-08-26
- Scope: CARE v6 benchmark import, quality, training, and evaluation jobs

## Context

CARE v6 contains semicolon-delimited event files with up to 957 columns and an
approximately 20 GiB source footprint. The online FastAPI dependency set must
remain small, an HTTP database transaction must never parse a full event or
train a model, and a C-farm event must be processed with bounded memory.

The evaluated choices were PyArrow, Polars, DuckDB, and Pandas. The required
operations are streaming CSV record batches, deterministic wide Parquet row
groups, column projection, schema serialization, and observable native memory.

## Decision

Use PyArrow 21.x as the only columnar engine and scikit-learn 1.x as the later
baseline-model engine. Both are in the `benchmark` optional dependency group;
the lock file currently resolves PyArrow 23.0.1 and scikit-learn 1.9.0. No
columnar or baseline package is imported by the online API at module import.

CARE jobs run through the independent `windops-care-pipeline` CLI or an
equivalent separately deployed worker. The job envelope supports the four
operations `import`, `quality`, `train`, and `evaluate`, with a persisted
heartbeat, progress, cancellation request, attempt count, resource statistics,
and content-verified checkpoint. FastAPI may later create, query, or request
cancellation of these jobs; it does not perform their heavy work.

The physical layout is one wide table per event:

```text
care/v6/standard/farm=<A|B|C>/event=<event_id>/data.parquet
```

The implementation reads CSV in 1 MiB blocks, writes Zstandard level 3, and
caps Parquet row groups at 8,192 rows. It records the source, schema, and final
content SHA-256 values. The published object name contains the full content
SHA-256 so concurrent retries cannot overwrite different bytes at one key.
Min/Max/Std are not split into sensor files, and split-specific files are not
introduced until a measured query workload proves a benefit.

Production uses the private `windops-care-benchmarks` bucket (or an explicitly
configured equivalent) with separate `raw`, `standard`, `quality`,
`predictions`, and `reports` prefixes. Versioning is required. Temporary
objects expire after 7 days; predictions after 1,825 days; the other governed
layers after 3,650 days. The bucket is included in the normal backup scope.

## Rejected alternatives

- Pandas was rejected because its normal CSV-to-frame path materializes the
  wide event and adds another dependency layer around Arrow output.
- Polars provides streaming operations, but adding it alongside PyArrow would
  duplicate the columnar runtime without an acceptance requirement that needs
  its expression engine.
- DuckDB is strong for analytical SQL, but the first delivery requires a
  deterministic conversion pipeline and per-batch checkpoints rather than an
  embedded query engine.
- One Parquet file per sensor was rejected because it creates thousands of
  small files and weakens event-level immutability.

## Consequences

Workers must install the `benchmark` extra and have bounded project-local work
storage. Online API images can omit that extra. Cancellation is cooperative at
confirmed record-batch boundaries. Confirmed chunks remain for a same-job
resume, while partial final files and failed object publications are removed.
Final metric ownership remains with the benchmark entities introduced in
CARE-H002/H004, preventing a file retry from duplicating metrics.

The decision is protected by unit tests for optional-import isolation, fixed
layout, column projection, bounded batches, cancellation/resume, immutable
retry, checkpoint tampering, failure cleanup, and unavailable object storage,
plus a read-only probe of a real C-farm file.
