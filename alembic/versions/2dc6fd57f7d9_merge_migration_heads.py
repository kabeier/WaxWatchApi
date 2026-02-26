"""merge migration heads

Revision ID: 2dc6fd57f7d9
Revises: 6f8e2b1a9c4d, ab12cd34ef56
Create Date: 2026-02-26 20:51:39.591840

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "2dc6fd57f7d9"
down_revision: str | Sequence[str] | None = ("6f8e2b1a9c4d", "ab12cd34ef56")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
