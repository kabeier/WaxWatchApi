"""normalize external account token lifecycle fields

Revision ID: ab12cd34ef56
Revises: d3aa9f1c7b21
Create Date: 2026-02-26 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ab12cd34ef56"
down_revision: str | Sequence[str] | None = "d3aa9f1c7b21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def extract_normalized_token_fields(token_metadata: dict | None) -> dict[str, object | None]:
    if not token_metadata:
        return {
            "refresh_token": None,
            "token_type": None,
            "access_token_expires_at": None,
            "scopes": None,
        }

    raw_scopes = token_metadata.get("oauth_scopes") or token_metadata.get("scopes")
    scopes: list[str] | None
    if isinstance(raw_scopes, list):
        scopes = [str(value) for value in raw_scopes if str(value).strip()]
    elif isinstance(raw_scopes, str):
        scopes = [value for value in raw_scopes.split(" ") if value]
    elif isinstance(token_metadata.get("scope"), str):
        scopes = [value for value in str(token_metadata["scope"]).split(" ") if value]
    else:
        scopes = None

    return {
        "refresh_token": token_metadata.get("refresh_token"),
        "token_type": token_metadata.get("token_type"),
        "access_token_expires_at": token_metadata.get("access_token_expires_at")
        or token_metadata.get("expires_at"),
        "scopes": scopes,
    }


def upgrade() -> None:
    op.add_column("external_account_links", sa.Column("refresh_token", sa.Text(), nullable=True))
    op.add_column(
        "external_account_links",
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("external_account_links", sa.Column("token_type", sa.String(length=50), nullable=True))
    op.add_column(
        "external_account_links",
        sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

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
                    WHEN NULLIF(BTRIM(token_metadata ->> 'scope'), '') IS NOT NULL
                        THEN to_jsonb(array_remove(regexp_split_to_array(BTRIM(token_metadata ->> 'scope'), E'\\s+'), ''))
                    ELSE NULL
                END
            )
        WHERE token_metadata IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_column("external_account_links", "scopes")
    op.drop_column("external_account_links", "token_type")
    op.drop_column("external_account_links", "access_token_expires_at")
    op.drop_column("external_account_links", "refresh_token")
