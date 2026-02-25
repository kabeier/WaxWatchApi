"""add discogs master identity and release match mode

Revision ID: 9d6c4ab8e2f1
Revises: f2a1c9b7d8e3, 52b7398d4aa3
Create Date: 2026-02-25 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9d6c4ab8e2f1"
down_revision: str | Sequence[str] | None = ("f2a1c9b7d8e3", "52b7398d4aa3")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("watch_releases", sa.Column("discogs_master_id", sa.Integer(), nullable=True))
    op.add_column(
        "watch_releases",
        sa.Column("match_mode", sa.String(length=30), server_default="exact_release", nullable=False),
    )

    op.drop_constraint("uq_watch_release_user_release", "watch_releases", type_="unique")
    op.create_check_constraint(
        "ck_watch_releases_match_mode_valid",
        "watch_releases",
        "match_mode IN ('exact_release', 'master_release')",
    )
    op.create_check_constraint(
        "ck_watch_releases_master_id_required",
        "watch_releases",
        "(match_mode != 'master_release') OR (discogs_master_id IS NOT NULL)",
    )
    op.create_index(
        "uq_watch_release_user_exact_release",
        "watch_releases",
        ["user_id", "discogs_release_id"],
        unique=True,
        postgresql_where=sa.text("match_mode = 'exact_release'"),
    )
    op.create_index(
        "uq_watch_release_user_master_release",
        "watch_releases",
        ["user_id", "discogs_master_id"],
        unique=True,
        postgresql_where=sa.text("match_mode = 'master_release'"),
    )

    op.add_column("listings", sa.Column("discogs_master_id", sa.Integer(), nullable=True))
    op.create_index(
        "ix_listings_discogs_master_id",
        "listings",
        ["discogs_master_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_listings_discogs_master_id", table_name="listings")
    op.drop_column("listings", "discogs_master_id")

    op.drop_index("uq_watch_release_user_master_release", table_name="watch_releases")
    op.drop_index("uq_watch_release_user_exact_release", table_name="watch_releases")
    op.drop_constraint("ck_watch_releases_master_id_required", "watch_releases", type_="check")
    op.drop_constraint("ck_watch_releases_match_mode_valid", "watch_releases", type_="check")
    op.create_unique_constraint(
        "uq_watch_release_user_release",
        "watch_releases",
        ["user_id", "discogs_release_id"],
    )

    op.drop_column("watch_releases", "match_mode")
    op.drop_column("watch_releases", "discogs_master_id")
