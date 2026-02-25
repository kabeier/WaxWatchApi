"""add notification delivery policy fields

Revision ID: 6f8e2b1a9c4d
Revises: a7b3c2d1e9f0
Create Date: 2026-02-26 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6f8e2b1a9c4d"
down_revision: str | Sequence[str] | None = "a7b3c2d1e9f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_notification_preferences",
        sa.Column("timezone_override", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "user_notification_preferences",
        sa.Column(
            "delivery_frequency",
            sa.String(length=20),
            nullable=False,
            server_default="instant",
        ),
    )
    op.alter_column("user_notification_preferences", "delivery_frequency", server_default=None)

    op.create_check_constraint(
        "ck_user_notification_preferences_delivery_frequency_valid",
        "user_notification_preferences",
        "delivery_frequency IN ('instant', 'hourly', 'daily')",
    )
    op.create_check_constraint(
        "ck_user_notification_preferences_quiet_hours_start_valid",
        "user_notification_preferences",
        "quiet_hours_start IS NULL OR (quiet_hours_start >= 0 AND quiet_hours_start <= 23)",
    )
    op.create_check_constraint(
        "ck_user_notification_preferences_quiet_hours_end_valid",
        "user_notification_preferences",
        "quiet_hours_end IS NULL OR (quiet_hours_end >= 0 AND quiet_hours_end <= 23)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_user_notification_preferences_quiet_hours_end_valid",
        "user_notification_preferences",
        type_="check",
    )
    op.drop_constraint(
        "ck_user_notification_preferences_quiet_hours_start_valid",
        "user_notification_preferences",
        type_="check",
    )
    op.drop_constraint(
        "ck_user_notification_preferences_delivery_frequency_valid",
        "user_notification_preferences",
        type_="check",
    )
    op.drop_column("user_notification_preferences", "delivery_frequency")
    op.drop_column("user_notification_preferences", "timezone_override")
