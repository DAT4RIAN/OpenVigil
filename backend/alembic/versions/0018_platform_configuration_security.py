"""Add platform configuration schema and historical secret-remediation evidence.

Revision ID: 0018_platform_configuration_security
Revises: 0017_knowledge_document_access_scope
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_platform_configuration_security"
down_revision: str | None = "0017_knowledge_document_access_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    json_type = postgresql.JSONB(astext_type=sa.Text())
    op.add_column(
        "platform_configuration_revisions",
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "platform_configuration_revisions",
        sa.Column("security_status", sa.String(48), nullable=False, server_default="clean"),
    )
    op.create_table(
        "platform_configuration_security_audits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "configuration_id",
            sa.String(36),
            sa.ForeignKey("platform_configuration_revisions.id"),
            nullable=False,
        ),
        sa.Column("configuration_key", sa.String(96), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("finding_categories", json_type, nullable=False),
        sa.Column("original_fingerprint", sa.String(64), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("rotation_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("replacement_secret_reference", sa.String(512)),
        sa.Column("rotation_evidence", sa.String(500)),
        sa.Column("rotation_confirmed_by", sa.String(160)),
        sa.Column("rotation_confirmed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("configuration_id", name="uq_platform_config_security_audit_revision"),
    )
    op.create_index(
        "ix_platform_config_security_audit_rotation",
        "platform_configuration_security_audits",
        ["rotation_required", "created_at"],
    )

    # The production target is PostgreSQL.  This first-pass migration removes
    # obvious legacy credentials before an application or backup can read the
    # upgraded database.  Startup then applies the strict Python schema scan to
    # every remaining revision and creates equally secret-free audit evidence.
    if op.get_context().dialect.name == "postgresql":
        suspected_material = (
            r"""CAST(value AS TEXT) ~* '"[^"}]*"""
            r"""(token|secret|password|passwd|private[^"}]*key|credential|"""
            r"""connection[^"}]*string|api[^"}]*key)[^"}]*"\s*:' """
            r"""OR CAST(value AS TEXT) ~* '"""
            r"""(password|passwd|pwd|token|secret|api[_ -]*key|credential)"""
            r"""\s*[:=]\s*[^ ,;"}]{6,}' """
            r"""OR CAST(value AS TEXT) ~* '-----BEGIN [^-]*PRIVATE KEY-----' """
            r"""OR reason ~* '"""
            r"""(password|passwd|pwd|token|secret|api[_ -]*key|credential)"""
            r"""\s*[:=]\s*[^ ,;]{6,}' """
        )
        op.execute(
            sa.text(
                f"""
                INSERT INTO platform_configuration_security_audits (
                    id, configuration_id, configuration_key, revision,
                    finding_categories, original_fingerprint, action,
                    rotation_required, created_at
                )
                SELECT id, id, configuration_key, revision,
                    CAST('["legacy_sensitive_material"]' AS JSONB),
                    md5(CAST(value AS TEXT) || reason || COALESCE(secret_reference, '')),
                    'quarantined_and_redacted', TRUE, CURRENT_TIMESTAMP
                FROM platform_configuration_revisions
                WHERE {suspected_material}
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                UPDATE platform_configuration_revisions
                SET value = CAST('{{}}' AS JSONB),
                    secret_reference = NULL,
                    reason = 'Security remediation removed the original configuration content.',
                    active = FALSE,
                    security_status = 'quarantined_rotation_required'
                WHERE {suspected_material}
                """
            )
        )

    op.alter_column("platform_configuration_revisions", "schema_version", server_default=None)
    op.alter_column("platform_configuration_revisions", "security_status", server_default=None)


def downgrade() -> None:
    op.drop_index(
        "ix_platform_config_security_audit_rotation",
        table_name="platform_configuration_security_audits",
    )
    op.drop_table("platform_configuration_security_audits")
    op.drop_column("platform_configuration_revisions", "security_status")
    op.drop_column("platform_configuration_revisions", "schema_version")
