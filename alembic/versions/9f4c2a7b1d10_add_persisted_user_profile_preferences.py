"""persist user profile preferences in database

Revision ID: 9f4c2a7b1d10
Revises: f2a1c9b7d8e3
Create Date: 2026-02-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f4c2a7b1d10"
down_revision: str | Sequence[str] | None = "f2a1c9b7d8e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("timezone", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("currency", sa.String(length=3), nullable=True))

    op.add_column(
        "user_notification_preferences",
        sa.Column("realtime_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("user_notification_preferences", "realtime_enabled", server_default=None)


def downgrade() -> None:
    op.drop_column("user_notification_preferences", "realtime_enabled")
    op.drop_column("users", "currency")
    op.drop_column("users", "timezone")
