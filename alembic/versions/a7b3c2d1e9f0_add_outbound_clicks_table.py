"""add outbound clicks table

Revision ID: a7b3c2d1e9f0
Revises: 9d6c4ab8e2f1, 9f4c2a7b1d10
Create Date: 2026-02-25 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7b3c2d1e9f0"
down_revision: str | Sequence[str] | None = ("9d6c4ab8e2f1", "9f4c2a7b1d10")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


provider_enum = postgresql.ENUM("discogs", "ebay", "mock", name="provider_enum", create_type=False)


def upgrade() -> None:
    op.create_table(
        "outbound_clicks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", provider_enum, nullable=False),
        sa.Column("referrer", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outbound_clicks_listing_created", "outbound_clicks", ["listing_id", "created_at"])
    op.create_index("ix_outbound_clicks_provider_created", "outbound_clicks", ["provider", "created_at"])
    op.create_index("ix_outbound_clicks_user_created", "outbound_clicks", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_outbound_clicks_user_created", table_name="outbound_clicks")
    op.drop_index("ix_outbound_clicks_provider_created", table_name="outbound_clicks")
    op.drop_index("ix_outbound_clicks_listing_created", table_name="outbound_clicks")
    op.drop_table("outbound_clicks")
