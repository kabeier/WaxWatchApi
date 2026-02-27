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
        WITH scope_candidates AS (
            SELECT
                eal.id,
                1 AS source_priority,
                to_jsonb(
                    ARRAY(
                        SELECT token
                        FROM jsonb_array_elements_text(eal.token_metadata -> 'oauth_scopes') AS token
                        WHERE BTRIM(token) <> ''
                    )
                ) AS normalized_scope_jsonb
            FROM external_account_links AS eal
            WHERE eal.scopes IS NULL
              AND eal.token_metadata IS NOT NULL
              AND jsonb_typeof(eal.token_metadata -> 'oauth_scopes') = 'array'

            UNION ALL

            SELECT
                eal.id,
                2 AS source_priority,
                to_jsonb(
                    ARRAY(
                        SELECT token
                        FROM jsonb_array_elements_text(eal.token_metadata -> 'scopes') AS token
                        WHERE BTRIM(token) <> ''
                    )
                ) AS normalized_scope_jsonb
            FROM external_account_links AS eal
            WHERE eal.scopes IS NULL
              AND eal.token_metadata IS NOT NULL
              AND jsonb_typeof(eal.token_metadata -> 'scopes') = 'array'

            UNION ALL

            SELECT
                eal.id,
                3 AS source_priority,
                CASE
                    WHEN NULLIF(
                        BTRIM(
                            regexp_replace(
                                COALESCE(eal.token_metadata ->> 'scopes', eal.token_metadata ->> 'scope'),
                                E'[[:space:]]+',
                                ' ',
                                'g'
                            )
                        ),
                        ''
                    ) IS NULL THEN NULL
                    ELSE to_jsonb(
                        array_remove(
                            string_to_array(
                                BTRIM(
                                    regexp_replace(
                                        COALESCE(
                                            eal.token_metadata ->> 'scopes',
                                            eal.token_metadata ->> 'scope'
                                        ),
                                        E'[[:space:]]+',
                                        ' ',
                                        'g'
                                    )
                                ),
                                ' '
                            ),
                            ''
                        )
                    )
                END AS normalized_scope_jsonb
            FROM external_account_links AS eal
            WHERE eal.scopes IS NULL
              AND eal.token_metadata IS NOT NULL
        ),
        ranked_scope_candidates AS (
            SELECT
                sc.id,
                sc.source_priority,
                sc.normalized_scope_jsonb,
                ROW_NUMBER() OVER (PARTITION BY sc.id ORDER BY sc.source_priority ASC) AS priority_rank
            FROM scope_candidates AS sc
            WHERE sc.normalized_scope_jsonb IS NOT NULL
              AND jsonb_array_length(sc.normalized_scope_jsonb) > 0
        )
        UPDATE external_account_links AS eal
        SET scopes = rsc.normalized_scope_jsonb
        FROM ranked_scope_candidates AS rsc
        WHERE eal.id = rsc.id
          AND rsc.priority_rank = 1
          AND eal.scopes IS NULL
        """
    )


def downgrade() -> None:
    pass
