"""Saved query revision history, so an edit no longer overwrites the old SQL.

Revision ID: 0004_saved_query_versions
Revises: 0003_refresh_tokens
Create Date: 2026-10-21 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_saved_query_versions"
down_revision: str | Sequence[str] | None = "0003_refresh_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "saved_query_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("saved_query_id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("sql_template", sa.Text(), nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["saved_query_id"],
            ["dbpilot.saved_queries.id"],
            name=op.f("fk_saved_query_versions_saved_query_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_query_versions")),
        sa.UniqueConstraint(
            "saved_query_id",
            "revision",
            name=op.f("uq_saved_query_versions_saved_query_id"),
        ),
        schema="dbpilot",
    )
    op.create_index(
        op.f("ix_saved_query_versions_saved_query_id"),
        "saved_query_versions",
        ["saved_query_id"],
        unique=False,
        schema="dbpilot",
    )

    # Every query saved before this migration has exactly one revision: what it
    # says today. Without this, its history would start empty and the first edit
    # would look like a brand new query.
    op.execute(
        """
        INSERT INTO dbpilot.saved_query_versions
            (saved_query_id, revision, sql_template, parameters, created_at)
        SELECT id, 1, sql_template, parameters, created_at
        FROM dbpilot.saved_queries
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_saved_query_versions_saved_query_id"),
        table_name="saved_query_versions",
        schema="dbpilot",
    )
    op.drop_table("saved_query_versions", schema="dbpilot")
