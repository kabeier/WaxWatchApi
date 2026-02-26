"""backfill normalized external account lifecycle fields

Revision ID: 7c9e1f2a4b6d
Revises: 2dc6fd57f7d9
Create Date: 2026-02-26 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c9e1f2a4b6d"
down_revision: str | Sequence[str] | None = "2dc6fd57f7d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE external_account_links
        SET
            refresh_token = COALESCE(refresh_token, token_metadata ->> 'refresh_token'),
            token_type = COALESCE(token_type, token_metadata ->> 'token_type'),
            access_token_expires_at = COALESCE(
                access_token_expires_at,
                CASE
                    WHEN token_metadata ->> 'access_token_expires_at' IS NOT NULL
                        THEN (token_metadata ->> 'access_token_expires_at')::timestamptz
                    WHEN token_metadata ->> 'expires_at' IS NOT NULL
                        THEN (token_metadata ->> 'expires_at')::timestamptz
                    ELSE NULL
                END
            ),
            scopes = COALESCE(
                scopes,
                CASE
                    WHEN jsonb_typeof(token_metadata -> 'oauth_scopes') = 'array'
                        THEN token_metadata -> 'oauth_scopes'
                    WHEN jsonb_typeof(token_metadata -> 'scopes') = 'array'
                        THEN token_metadata -> 'scopes'
                    WHEN token_metadata ->> 'scopes' IS NOT NULL
                        THEN to_jsonb(regexp_split_to_array(token_metadata ->> 'scopes', E'\\s+'))
                    WHEN token_metadata ->> 'scope' IS NOT NULL
                        THEN to_jsonb(regexp_split_to_array(token_metadata ->> 'scope', E'\\s+'))
                    ELSE NULL
                END
            )
        WHERE token_metadata IS NOT NULL
        """
    )


def downgrade() -> None:
    pass
