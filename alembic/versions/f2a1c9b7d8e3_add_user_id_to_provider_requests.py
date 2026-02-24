"""add user id to provider requests

Revision ID: f2a1c9b7d8e3
Revises: e1c3f8a9d2b4
Create Date: 2026-02-24 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2a1c9b7d8e3"
down_revision: str | Sequence[str] | None = "e1c3f8a9d2b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SYSTEM_PROVIDER_REQUEST_USER_ID = "00000000-0000-0000-0000-000000000001"
SYSTEM_PROVIDER_REQUEST_USER_EMAIL = "system-provider-requests@waxwatch.local"


def upgrade() -> None:
    op.add_column(
        "provider_requests",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    bind = op.get_bind()

    bind.execute(
        sa.text(
            """
            INSERT INTO users (id, email, hashed_password, display_name, is_active, created_at, updated_at)
            VALUES (
                :id,
                :email,
                '!',
                'System Provider Requests',
                false,
                timezone('utc', now()),
                timezone('utc', now())
            )
            ON CONFLICT (email) DO NOTHING
            """
        ),
        {
            "id": SYSTEM_PROVIDER_REQUEST_USER_ID,
            "email": SYSTEM_PROVIDER_REQUEST_USER_EMAIL,
        },
    )

    bind.execute(
        sa.text(
            """
            UPDATE provider_requests
            SET user_id = :id::uuid
            WHERE user_id IS NULL
            """
        ),
        {"id": SYSTEM_PROVIDER_REQUEST_USER_ID},
    )

    op.alter_column("provider_requests", "user_id", nullable=False)
    op.create_foreign_key(
        "fk_provider_requests_user_id_users",
        "provider_requests",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_index(
        "ix_provider_requests_user_created_at",
        "provider_requests",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_provider_requests_user_provider_created_at",
        "provider_requests",
        ["user_id", "provider", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_provider_requests_user_provider_created_at", table_name="provider_requests")
    op.drop_index("ix_provider_requests_user_created_at", table_name="provider_requests")
    op.drop_constraint("fk_provider_requests_user_id_users", "provider_requests", type_="foreignkey")
    op.drop_column("provider_requests", "user_id")
