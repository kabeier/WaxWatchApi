from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.services.rule_runner import run_rule_once

router = APIRouter(prefix="/dev", tags=["dev"])


def get_current_user_id(x_user_id: UUID = Header(..., alias="X-User-Id")) -> UUID:
    return x_user_id


@router.post("/rules/{rule_id}/run")
def run_rule(
    rule_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
    limit: int = Query(20, ge=1, le=50),
):
    try:
        summary = run_rule_once(db, user_id=user_id, rule_id=rule_id, limit=limit)
    except ValueError:
        raise HTTPException(status_code=404, detail="Rule not found")

    return {
        "rule_id": str(summary.rule_id),
        "fetched": summary.fetched,
        "listings_created": summary.listings_created,
        "snapshots_created": summary.snapshots_created,
        "matches_created": summary.matches_created,
    }