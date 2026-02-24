from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, Query
from sqlalchemy import and_, or_
from sqlalchemy.orm import Query as SAQuery


@dataclass(frozen=True)
class PaginationParams:
    limit: int
    offset: int
    cursor: str | None
    cursor_created_at: datetime | None
    cursor_id: UUID | None


def encode_created_id_cursor(*, created_at: datetime, row_id: UUID) -> str:
    payload = f"{created_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8")


def _decode_created_id_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        created_at_raw, row_id_raw = raw.split("|", maxsplit=1)
        return datetime.fromisoformat(created_at_raw), UUID(row_id_raw)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="invalid cursor") from None


def get_pagination_params(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    cursor: str | None = Query(default=None),
) -> PaginationParams:
    if cursor is not None and offset > 0:
        raise HTTPException(status_code=422, detail="offset cannot be used with cursor")

    cursor_created_at: datetime | None = None
    cursor_id: UUID | None = None
    if cursor is not None:
        cursor_created_at, cursor_id = _decode_created_id_cursor(cursor)

    return PaginationParams(
        limit=limit,
        offset=offset,
        cursor=cursor,
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
    )


def apply_created_id_pagination(query: SAQuery, model, params: PaginationParams) -> SAQuery:
    query = query.order_by(model.created_at.desc(), model.id.desc())

    if params.cursor_created_at is not None and params.cursor_id is not None:
        query = query.filter(
            or_(
                model.created_at < params.cursor_created_at,
                and_(
                    model.created_at == params.cursor_created_at,
                    model.id < params.cursor_id,
                ),
            )
        )
    elif params.offset:
        query = query.offset(params.offset)

    return query.limit(params.limit)
