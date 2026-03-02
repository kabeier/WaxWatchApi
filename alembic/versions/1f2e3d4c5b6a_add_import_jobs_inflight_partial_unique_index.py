"""add partial unique index for in-flight import jobs

Revision ID: 1f2e3d4c5b6a
Revises: 7c9e1f2a4b6d
Create Date: 2026-03-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1f2e3d4c5b6a"
down_revision: str | Sequence[str] | None = "7c9e1f2a4b6d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_import_jobs_inflight_user_provider_scope",
        "import_jobs",
        ["user_id", "provider", "import_scope"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_import_jobs_inflight_user_provider_scope", table_name="import_jobs")
