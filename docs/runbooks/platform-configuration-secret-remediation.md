# Platform configuration secret remediation

This runbook applies when migration or startup scanning finds credential-like material in a
historical `platform_configuration_revisions` or `ingest_sources.credential_secret_reference` row.

## Safety behavior

- Migration `0018_platform_configuration_security` quarantines obvious PostgreSQL JSON or reason
  fields, and migration `0021_ingest_source_secret_audits` quarantines unsafe data-source
  references before the upgraded application or a new backup reads them.
- Every API startup scans all remaining revisions with the same recursive, case-insensitive policy
  used for new requests. Invalid rows are deactivated, their value and reason are replaced, and a
  value-free `platform_configuration_security_audits` record is created.
- A production `/api/v1/readyz` response remains `503` while any audit has
  `rotation_required=true`. Do not bypass this gate.
- Full values and remediation evidence are restricted to an explicitly global
  `operations_manager`. Other human roles may read only `/api/v1/platform/configuration-status`.

## Operator procedure

1. Stop configuration writes and preserve database audit logs. Do not copy the suspect JSON into a
   ticket, terminal transcript, chat, or application log.
2. Apply Alembic through `0026_schema_contract_alignment` and start one API instance. Confirm
   the redacted status reports `attention_required` without returning a value.
3. As a globally authorized operations manager, read `/api/v1/platform/configurations` and record
   only the security audit ID, configuration key, revision, finding categories, and fingerprint.
4. In the owning external Secret Manager, revoke the suspected credential, create a replacement,
   and update every dependent system. The replacement value must never enter WindOps JSON.
5. Confirm the rotation through the authenticated production Worker gateway using
   `POST /api/backend/platform/configuration-security-audits/{audit_id}/rotation-confirmation`
   (or the data-source equivalent
   `/api/backend/platform/data-source-security-audits/{audit_id}/rotation-confirmation`) with a
   supported external reference and a non-secret change-ticket description. The Worker forwards
   the request to the FastAPI `/api/v1/...` route and enforces POST-only, Sites delegation,
   nonce/replay, and `Idempotency-Key` checks; do not call an unlisted wildcard path.
6. Create a new, schema-valid configuration revision if the quarantined policy is still required.
   Never reactivate or edit the historical row.
7. Inventory database dumps, support bundles, browser exports, and log archives created before the
   remediation time. Revoke access, expire or securely delete contaminated copies under the
   organization retention policy, and record that disposition in the incident ticket.
8. Only after `pending_credential_rotations` is zero, create and verify a new backup. Preserve the
   security audit and change-ticket evidence; do not preserve the original submitted value.

## Verification

The release owner must verify all of the following:

- `/api/v1/readyz` is ready and the redacted status reports zero pending rotations.
- The full manager response contains no Secret Manager reference value or submitted credential.
- Domain events contain audit IDs and revision metadata only.
- A search of the post-remediation database dump, application logs, and newly created backup for
  the incident's controlled test marker returns no match.
- The external secret owner confirms revocation and replacement in the referenced change ticket.

If any item fails, keep the deployment unready and continue incident handling.
