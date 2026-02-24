"""add discogs integration account links and import jobs

Revision ID: c3e52b2f7e1a
Revises: 8b5f4f94f2b1
Create Date: 2026-02-23 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3e52b2f7e1a"
down_revision: str | Sequence[str] | None = "8b5f4f94f2b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE event_type_enum ADD VALUE IF NOT EXISTS 'IMPORT_STARTED'")
    op.execute("ALTER TYPE event_type_enum ADD VALUE IF NOT EXISTS 'IMPORT_COMPLETED'")
    op.execute("ALTER TYPE event_type_enum ADD VALUE IF NOT EXISTS 'IMPORT_FAILED'")

    op.create_table(
        "external_account_links",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "provider",
            sa.Enum("discogs", "ebay", "musicbrainz", "spotify", "mock", name="provider_enum"),
            nullable=False,
        ),
        sa.Column("external_user_id", sa.String(length=120), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("token_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", name="uq_external_account_links_user_provider"),
    )
    op.create_index(
        "ix_external_account_links_provider_external_user",
        "external_account_links",
        ["provider", "external_user_id"],
        unique=False,
    )

    op.create_table(
        "import_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("external_account_link_id", sa.UUID(), nullable=True),
        sa.Column(
            "provider",
            sa.Enum("discogs", "ebay", "musicbrainz", "spotify", "mock", name="provider_enum"),
            nullable=False,
        ),
        sa.Column("import_scope", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("cursor", sa.String(length=255), nullable=True),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("processed_count", sa.Integer(), nullable=False),
        sa.Column("imported_count", sa.Integer(), nullable=False),
        sa.Column("created_count", sa.Integer(), nullable=False),
        sa.Column("updated_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("errors", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["external_account_link_id"], ["external_account_links.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_jobs_status", "import_jobs", ["status"], unique=False)
    op.create_index("ix_import_jobs_user_created", "import_jobs", ["user_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_import_jobs_user_created", table_name="import_jobs")
    op.drop_index("ix_import_jobs_status", table_name="import_jobs")
    op.drop_table("import_jobs")
    op.drop_index("ix_external_account_links_provider_external_user", table_name="external_account_links")
    op.drop_table("external_account_links")
