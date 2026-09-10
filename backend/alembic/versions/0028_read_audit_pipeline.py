"""Partition, batch, archive, and bound business-read audit records.

Revision ID: 0028_read_audit_pipeline
Revises: 0027_quality_artifact_stages
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028_read_audit_pipeline"
down_revision: str | None = "0027_quality_artifact_stages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_archive_table() -> None:
    op.create_table(
        "read_access_audit_archives",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("schema", sa.String(64), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("payload_gzip", sa.LargeBinary(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("row_count > 0", name="ck_read_access_archive_row_count"),
        sa.CheckConstraint("period_end >= period_start", name="ck_read_access_archive_period"),
        sa.CheckConstraint("expires_at > period_end", name="ck_read_access_archive_expiry"),
    )
    op.create_index(
        "ix_read_access_archive_period",
        "read_access_audit_archives",
        ["period_start", "period_end"],
    )
    op.create_index(
        "ix_read_access_archive_expires",
        "read_access_audit_archives",
        ["expires_at"],
    )


def _postgresql_upgrade() -> None:
    op.drop_index("ix_read_access_subject_accessed", table_name="read_access_audits")
    op.rename_table("read_access_audits", "read_access_audits_legacy")
    op.execute(
        """
        CREATE TABLE read_access_audits (
          id varchar(36) NOT NULL,
          subject varchar(160) NOT NULL,
          role varchar(96) NOT NULL,
          method varchar(16) NOT NULL,
          endpoint varchar(320) NOT NULL,
          query jsonb NOT NULL DEFAULT '{}'::jsonb,
          accessed_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (accessed_at, id)
        ) PARTITION BY RANGE (accessed_at)
        """
    )
    op.execute("CREATE TABLE read_access_audits_default PARTITION OF read_access_audits DEFAULT")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION windops_ensure_read_audit_partitions(months_ahead integer)
        RETURNS void
        LANGUAGE plpgsql
        SECURITY INVOKER
        SET search_path = public, pg_temp
        AS $$
        DECLARE
          offset_month integer;
          lower_bound timestamptz;
          upper_bound timestamptz;
          partition_name text;
        BEGIN
          IF months_ahead < 1 OR months_ahead > 24 THEN
            RAISE EXCEPTION 'read audit months_ahead outside 1..24';
          END IF;
          FOR offset_month IN -1..months_ahead LOOP
            lower_bound := date_trunc('month', now()) + make_interval(months => offset_month);
            upper_bound := lower_bound + interval '1 month';
            partition_name := 'read_access_audits_' || to_char(lower_bound, 'YYYYMM');
            EXECUTE format(
              'CREATE TABLE IF NOT EXISTS %I PARTITION OF read_access_audits '
              'FOR VALUES FROM (%L) TO (%L)',
              partition_name,
              lower_bound,
              upper_bound
            );
          END LOOP;
        END;
        $$
        """
    )
    op.execute("SELECT windops_ensure_read_audit_partitions(3)")
    op.execute(
        """
        INSERT INTO read_access_audits
          (id, subject, role, method, endpoint, query, accessed_at)
        SELECT id, subject, role, method, endpoint, query, accessed_at
        FROM read_access_audits_legacy
        """
    )
    op.drop_table("read_access_audits_legacy")
    op.create_index(
        "ix_read_access_subject_accessed",
        "read_access_audits",
        ["subject", "accessed_at"],
    )
    op.create_index(
        "ix_read_access_endpoint_accessed",
        "read_access_audits",
        ["endpoint", "accessed_at"],
    )


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        _postgresql_upgrade()
    else:
        op.create_index(
            "ix_read_access_endpoint_accessed",
            "read_access_audits",
            ["endpoint", "accessed_at"],
        )
    _create_archive_table()


def _postgresql_downgrade() -> None:
    op.drop_index("ix_read_access_endpoint_accessed", table_name="read_access_audits")
    op.drop_index("ix_read_access_subject_accessed", table_name="read_access_audits")
    op.rename_table("read_access_audits", "read_access_audits_partitioned")
    op.create_table(
        "read_access_audits",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("subject", sa.String(160), nullable=False),
        sa.Column("role", sa.String(96), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("endpoint", sa.String(320), nullable=False),
        sa.Column(
            "query",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "accessed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute(
        """
        INSERT INTO read_access_audits
          (id, subject, role, method, endpoint, query, accessed_at)
        SELECT id, subject, role, method, endpoint, query, accessed_at
        FROM read_access_audits_partitioned
        """
    )
    op.drop_table("read_access_audits_partitioned")
    op.create_index(
        "ix_read_access_subject_accessed",
        "read_access_audits",
        ["subject", "accessed_at"],
    )
    op.execute("DROP FUNCTION windops_ensure_read_audit_partitions(integer)")


def downgrade() -> None:
    op.drop_index("ix_read_access_archive_expires", table_name="read_access_audit_archives")
    op.drop_index("ix_read_access_archive_period", table_name="read_access_audit_archives")
    op.drop_table("read_access_audit_archives")
    if op.get_bind().dialect.name == "postgresql":
        _postgresql_downgrade()
    else:
        op.drop_index("ix_read_access_endpoint_accessed", table_name="read_access_audits")
