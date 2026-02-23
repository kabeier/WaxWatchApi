"""add mock to provider enum

Revision ID: 8b5f4f94f2b1
Revises: 52b7398d4aa3
Create Date: 2026-02-23 00:00:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "8b5f4f94f2b1"
down_revision = "52b7398d4aa3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE provider_enum ADD VALUE IF NOT EXISTS 'mock'")


def downgrade() -> None:
    # PostgreSQL enums cannot safely drop values without type recreation.
    pass
