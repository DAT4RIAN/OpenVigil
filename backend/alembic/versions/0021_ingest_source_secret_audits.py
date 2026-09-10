"""Add secret-free audit evidence for legacy ingest source credentials.

Revision ID: 0021_ingest_source_secret_audits
Revises: 0020_delegated_replay_and_idempotency
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_ingest_source_secret_audits"
down_revision: str | None = "0020_delegated_replay_and_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    json_type = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "ingest_source_security_audits",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "source_id",
            sa.String(length=96),
            sa.ForeignKey("ingest_sources.id"),
            nullable=False,
        ),
        sa.Column("finding_categories", json_type, nullable=False),
        sa.Column("original_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("rotation_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("replacement_secret_reference", sa.String(length=512)),
        sa.Column("rotation_evidence", sa.String(length=500)),
        sa.Column("rotation_confirmed_by", sa.String(length=160)),
        sa.Column("rotation_confirmed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "source_id",
            "original_fingerprint",
            name="uq_ingest_source_security_audit_fingerprint",
        ),
    )
    op.create_index(
        "ix_ingest_source_security_audit_rotation",
        "ingest_source_security_audits",
        ["rotation_required", "created_at"],
    )

    # PostgreSQL performs a first-pass quarantine before application startup.
    # The Python remediation pass repeats the strict URI validation for every
    # dialect and catches values that are not expressible as this conservative
    # SQL pattern.
    if op.get_context().dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                INSERT INTO ingest_source_security_audits (
                    id, source_id, finding_categories, original_fingerprint,
                    action, rotation_required, created_at
                )
                SELECT
                    md5(id || ':' || credential_secret_reference),
                    id,
                    CAST('["invalid_secret_reference"]' AS JSONB),
                    md5(credential_secret_reference || CHR(58) || 'windops-audit-1') ||
                        md5(credential_secret_reference || CHR(58) || 'windops-audit-2'),
                    'quarantined_and_redacted', TRUE, CURRENT_TIMESTAMP
                FROM ingest_sources
                WHERE credential_secret_reference IS NOT NULL
                  AND (
                    credential_secret_reference !~* '^(vault|aws-secretsmanager|azure-keyvault|gcp-secretmanager)://[^[:space:]/]+/[^[:space:]]+$'
                    OR credential_secret_reference ~ '[@?\\s]'
                    OR credential_secret_reference ~ '/\\.(\\.?)(/|$)'
                  )
                ON CONFLICT (source_id, original_fingerprint) DO NOTHING
                """
            )
        )
        op.execute(
            sa.text(
                """
                UPDATE ingest_sources
                SET credential_secret_reference = NULL,
                    enabled = FALSE,
                    status = 'quarantined'
                WHERE credential_secret_reference IS NOT NULL
                  AND EXISTS (
                    SELECT 1
                    FROM ingest_source_security_audits audit
                    WHERE audit.source_id = ingest_sources.id
                      AND audit.rotation_required = TRUE
                  )
                """
            )
        )


def downgrade() -> None:
    op.drop_index(
        "ix_ingest_source_security_audit_rotation",
        table_name="ingest_source_security_audits",
    )
    op.drop_table("ingest_source_security_audits")
