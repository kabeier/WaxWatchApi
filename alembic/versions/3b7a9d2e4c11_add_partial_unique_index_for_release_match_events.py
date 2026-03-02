"""add partial unique index for release match events

Revision ID: 3b7a9d2e4c11
Revises: 9f4c2a7b1d10, ab12cd34ef56, 52b7398d4aa3, 6f8e2b1a9c4d, 1f2e3d4c5b6a
Create Date: 2026-03-02 00:00:01.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3b7a9d2e4c11"
down_revision: str | Sequence[str] | None = (
    "9f4c2a7b1d10",
    "ab12cd34ef56",
    "52b7398d4aa3",
    "6f8e2b1a9c4d",
    "1f2e3d4c5b6a",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_events_new_match_watch_release_listing",
        "events",
        ["user_id", "type", "watch_release_id", "listing_id"],
        unique=True,
        postgresql_where=sa.text(
            "type = 'NEW_MATCH' AND watch_release_id IS NOT NULL AND listing_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_events_new_match_watch_release_listing", table_name="events")
