# CARE v6 artifact governance

## License boundary

WindOps source code remains under the repository's MIT `LICENSE`. CARE v6 source
data and every derived CARE data artifact are a separate licensing domain under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). No CARE raw,
standard, prediction, quality, or report data file may be added to Git or a
frontend build.

The authoritative source is “Wind Turbine SCADA Data For Early Fault Detection”
by Christian Gück and Cyriana M. A. Roelofs, Fraunhofer Institute for Energy
Economics and Energy System Technology, Zenodo DOI
[`10.5281/zenodo.15846963`](https://zenodo.org/records/15846963). The immutable
manifest and `windops_backend.benchmarks.care.licensing` contain the complete
recommended citation used on artifacts.

Every wide Parquet embeds the dataset attribution, citation, DOI, license name
and URL, `changes_made`, transformation versions, source hashes and a pointer to
its immutable content-hash sidecar. JSON artifacts include an intrinsic
document hash and a complete license object. Object keys and parent manifests
carry the final file SHA-256; this avoids an impossible self-referential hash
inside the bytes being hashed.

## Access isolation

- CARE uses its own validated bucket and the private `care/v6/raw`, `standard`,
  `quality`, `predictions`, and `reports` prefixes. Configuration rejects reuse
  of a field-evidence, knowledge, model, or twin production bucket.
- The import worker has no delete permission. The API and browser do not receive
  object-store credentials.
- Catalog and replay summaries require `benchmark`; evaluation exports also
  require `model` and `benchmark_export`. Truth and fault descriptions require
  the independent `benchmark_truth` scope.
- Dataset tenant filters and replay turbine scope checks remain authoritative;
  a cross-tenant identifier is returned as not found.
- Raw and standard object download routes do not exist. The production gateway
  allowlist rejects raw paths.

## Governed report export

Use `POST /api/v1/benchmarks/evaluations/{evaluation_run_id}/exports` with an
explicit `json` or `csv` format, source evaluation SHA-256, `changesMade`, and
the required `Idempotency-Key` header. The response contains the full data license metadata and
payload hash; response headers contain the final byte SHA-256 and durable audit
event ID. Reusing the same key returns identical bytes; using it for a different
request fails closed.

External distribution additionally requires positive confirmation of
attribution, the CC BY-SA link, ShareAlike obligations, and a non-empty legal or
compliance review reference. A failed review writes an immutable denied audit
event before returning 403. This engineering gate does not replace legal advice.

## Derived-artifact cleanup

Raw CARE data is never cleanup-eligible. A cleanup worker may temporarily assume
`backend/deploy/care-minio-cleanup-policy.json`, which excludes `raw` and is kept
separate from normal workers. Before deletion it must:

1. create `CareArtifactCleanupScope` with the exact CARE v6 content hash and
   either a farm/event partition or model/evaluation-run identity;
2. list no more than 256 objects below the computed prefix;
3. require the reviewed object-name/SHA-256 set to match the listing exactly;
4. re-read every object SHA-256 and supply the exact scope hash as confirmation;
5. call the audited `execute_care_artifact_cleanup` orchestrator with a unique
   cleanup ID. It commits an immutable `benchmark.cleanup.started` intent before
   deletion and a `completed`, `failed`, or `rejected` outcome afterward. The
   same completed request is replay-safe; interrupted or failed identities
   require human reconciliation and a newly reviewed cleanup ID.

Do not call the internal object deletion primitive directly. The orchestrator
is the production entry point so an irreversible deletion cannot rely on a
caller remembering to append an audit event.

Never broaden a cleanup prefix, use a wildcard dataset/run identity, or attach
the cleanup policy to the API, browser, import worker, or production asset
service accounts.
