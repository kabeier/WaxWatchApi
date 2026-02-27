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

    op.execute(
        """
        WITH scope_sources AS (
            SELECT
                eal.id,
                CASE
                    WHEN jsonb_typeof(eal.token_metadata -> 'oauth_scopes') = 'array' THEN (
                        SELECT to_jsonb(ARRAY_AGG(token))
                        FROM (
                            SELECT BTRIM(value) AS token
                            FROM jsonb_array_elements_text(eal.token_metadata -> 'oauth_scopes')
                        ) normalized
                        WHERE token <> ''
                    )
                    ELSE NULL
                END AS oauth_scopes_jsonb,
                CASE
                    WHEN jsonb_typeof(eal.token_metadata -> 'scopes') = 'array' THEN (
                        SELECT to_jsonb(ARRAY_AGG(token))
                        FROM (
                            SELECT BTRIM(value) AS token
                            FROM jsonb_array_elements_text(eal.token_metadata -> 'scopes')
                        ) normalized
                        WHERE token <> ''
                    )
                    ELSE NULL
                END AS scopes_array_jsonb,
                (
                    SELECT
                        CASE
                            WHEN NULLIF(normalized_scope_text, '') IS NULL THEN NULL
                            ELSE to_jsonb(array_remove(string_to_array(normalized_scope_text, ' '), ''))
                        END
                    FROM (
                        SELECT BTRIM(
                            regexp_replace(
                                COALESCE(eal.token_metadata ->> 'scopes', eal.token_metadata ->> 'scope'),
                                E'[[:space:]]+',
                                ' ',
                                'g'
                            )
                        ) AS normalized_scope_text
                    ) text_scope
                ) AS scopes_text_jsonb
            FROM external_account_links AS eal
            WHERE eal.scopes IS NULL
              AND eal.token_metadata IS NOT NULL
        ),
        scope_normalized AS (
            SELECT
                ss.id,
                COALESCE(
                    CASE
                        WHEN ss.oauth_scopes_jsonb IS NOT NULL
                            AND jsonb_array_length(ss.oauth_scopes_jsonb) > 0 THEN ss.oauth_scopes_jsonb
                        ELSE NULL
                    END,
                    CASE
                        WHEN ss.scopes_array_jsonb IS NOT NULL
                            AND jsonb_array_length(ss.scopes_array_jsonb) > 0 THEN ss.scopes_array_jsonb
                        ELSE NULL
                    END,
                    CASE
                        WHEN ss.scopes_text_jsonb IS NOT NULL
                            AND jsonb_array_length(ss.scopes_text_jsonb) > 0 THEN ss.scopes_text_jsonb
                        ELSE NULL
                    END
                ) AS normalized_scope_jsonb
            FROM scope_sources AS ss
        )
        UPDATE external_account_links AS eal
        SET scopes = sn.normalized_scope_jsonb
        FROM scope_normalized AS sn
        WHERE eal.id = sn.id
          AND eal.scopes IS NULL
          AND sn.normalized_scope_jsonb IS NOT NULL
          AND jsonb_array_length(sn.normalized_scope_jsonb) > 0
        """
    )


def downgrade() -> None:
    pass
