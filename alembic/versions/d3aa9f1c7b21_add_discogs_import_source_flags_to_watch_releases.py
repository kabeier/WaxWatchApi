"""add discogs import source flags to watch releases

Revision ID: d3aa9f1c7b21
Revises: 9d6c4ab8e2f1
Create Date: 2026-02-25 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3aa9f1c7b21"
down_revision: str | Sequence[str] | None = "9d6c4ab8e2f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "watch_releases",
        sa.Column("imported_from_wantlist", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "watch_releases",
        sa.Column("imported_from_collection", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.alter_column("watch_releases", "imported_from_wantlist", server_default=None)
    op.alter_column("watch_releases", "imported_from_collection", server_default=None)


def downgrade() -> None:
    op.drop_column("watch_releases", "imported_from_collection")
    op.drop_column("watch_releases", "imported_from_wantlist")
