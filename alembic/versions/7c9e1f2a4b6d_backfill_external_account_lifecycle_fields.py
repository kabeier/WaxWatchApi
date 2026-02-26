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
            )
        WHERE token_metadata IS NOT NULL
        """
    )

    # Priority path: preserve first-class array metadata values when scopes is unset.
    op.execute(
        """
        UPDATE external_account_links
        SET scopes = CASE
            WHEN jsonb_typeof(token_metadata -> 'oauth_scopes') = 'array' THEN token_metadata -> 'oauth_scopes'
            WHEN jsonb_typeof(token_metadata -> 'scopes') = 'array' THEN token_metadata -> 'scopes'
            ELSE scopes
        END
        WHERE scopes IS NULL
          AND token_metadata IS NOT NULL
          AND (
            jsonb_typeof(token_metadata -> 'oauth_scopes') = 'array'
            OR jsonb_typeof(token_metadata -> 'scopes') = 'array'
          )
        """
    )

    # Deterministic string normalization path via CTE:
    # 1) derive raw text from metadata (scopes -> scope fallback),
    # 2) collapse whitespace/trim,
    # 3) split on single-space and drop empty tokens,
    # 4) write only non-empty arrays and only for rows with null scopes.
    op.execute(
        """
        WITH scope_candidates AS (
            SELECT
                eal.id,
                BTRIM(
                    regexp_replace(
                        COALESCE(eal.token_metadata ->> 'scopes', eal.token_metadata ->> 'scope'),
                        E'[[:space:]]+',
                        ' ',
                        'g'
                    )
                ) AS raw_scope_text
            FROM external_account_links AS eal
            WHERE eal.scopes IS NULL
              AND eal.token_metadata IS NOT NULL
        ),
        normalized_scope_candidates AS (
            SELECT
                sc.id,
                sc.raw_scope_text,
                CASE
                    WHEN NULLIF(sc.raw_scope_text, '') IS NULL THEN NULL
                    ELSE to_jsonb(array_remove(string_to_array(sc.raw_scope_text, ' '), ''))
                END AS normalized_scope_jsonb
            FROM scope_candidates AS sc
        )
        UPDATE external_account_links AS eal
        SET scopes = nsc.normalized_scope_jsonb
        FROM normalized_scope_candidates AS nsc
        WHERE eal.id = nsc.id
          AND eal.scopes IS NULL
          AND nsc.normalized_scope_jsonb IS NOT NULL
          AND jsonb_array_length(nsc.normalized_scope_jsonb) > 0
        """
    )


def downgrade() -> None:
    pass
