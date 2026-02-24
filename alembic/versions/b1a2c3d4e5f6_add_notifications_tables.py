"""add notifications and user notification preferences

Revision ID: b1a2c3d4e5f6
Revises: c3e52b2f7e1a
Create Date: 2026-02-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1a2c3d4e5f6"
down_revision: str | Sequence[str] | None = "c3e52b2f7e1a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    notification_channel_enum = postgresql.ENUM(
        "email", "realtime", name="notification_channel_enum", create_type=False
    )
    notification_status_enum = postgresql.ENUM(
        "pending", "sent", "failed", name="notification_status_enum", create_type=False
    )
    notification_channel_enum.create(op.get_bind(), checkfirst=True)
    notification_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "RULE_CREATED",
                "RULE_UPDATED",
                "RULE_DISABLED",
                "RULE_ENABLED",
                "WATCH_RELEASE_CREATED",
                "WATCH_RELEASE_UPDATED",
                "WATCH_RELEASE_DISABLED",
                "WATCH_RELEASE_ENABLED",
                "LISTING_FIRST_SEEN",
                "LISTING_PRICE_DROP",
                "LISTING_PRICE_RISE",
                "LISTING_ENDED",
                "NEW_MATCH",
                "IMPORT_STARTED",
                "IMPORT_COMPLETED",
                "IMPORT_FAILED",
                name="event_type_enum",
            ),
            nullable=False,
        ),
        sa.Column("channel", notification_channel_enum, nullable=False),
        sa.Column("status", notification_status_enum, nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "channel", name="uq_notifications_event_channel"),
    )
    op.create_index("ix_notifications_status", "notifications", ["status"], unique=False)
    op.create_index(
        "ix_notifications_user_created_at",
        "notifications",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index("ix_notifications_user_read", "notifications", ["user_id", "is_read"], unique=False)

    op.create_table(
        "user_notification_preferences",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("email_enabled", sa.Boolean(), nullable=False),
        sa.Column("quiet_hours_start", sa.Integer(), nullable=True),
        sa.Column("quiet_hours_end", sa.Integer(), nullable=True),
        sa.Column("event_toggles", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        "ix_user_notification_preferences_user",
        "user_notification_preferences",
        ["user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_user_notification_preferences_user", table_name="user_notification_preferences")
    op.drop_table("user_notification_preferences")

    op.drop_index("ix_notifications_user_read", table_name="notifications")
    op.drop_index("ix_notifications_user_created_at", table_name="notifications")
    op.drop_index("ix_notifications_status", table_name="notifications")
    op.drop_table("notifications")

    notification_status_enum = postgresql.ENUM(
        "pending", "sent", "failed", name="notification_status_enum", create_type=False
    )
    notification_channel_enum = postgresql.ENUM(
        "email", "realtime", name="notification_channel_enum", create_type=False
    )
    notification_status_enum.drop(op.get_bind(), checkfirst=True)
    notification_channel_enum.drop(op.get_bind(), checkfirst=True)
