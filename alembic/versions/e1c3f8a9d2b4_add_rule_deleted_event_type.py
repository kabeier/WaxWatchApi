"""add RULE_DELETED to event_type_enum

Revision ID: e1c3f8a9d2b4
Revises: b1a2c3d4e5f6
Create Date: 2026-02-24 00:00:01.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1c3f8a9d2b4"
down_revision: str | Sequence[str] | None = "b1a2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE event_type_enum ADD VALUE IF NOT EXISTS 'RULE_DELETED'")


def downgrade() -> None:
    # Postgres enums do not support dropping a value safely in-place.
    pass
