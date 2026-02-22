from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.logging import get_logger
from app.services.rule_runner import run_rule_once

logger = get_logger(__name__)
router = APIRouter(prefix="/dev", tags=["dev"])


def get_current_user_id(x_user_id: str = Header(..., alias="X-User-Id")) -> UUID:
    return UUID(x_user_id)


@router.post("/rules/{rule_id}/run")
def run_rule(
    request: Request,
    rule_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
    limit: int = Query(20, ge=1, le=50),
):
    request_id = getattr(request.state, "request_id", "-")

    logger.info(
        "dev.rule_run.call",
        extra={"request_id": request_id, "user_id": str(user_id), "rule_id": str(rule_id), "limit": limit},
    )

    try:
        summary = run_rule_once(db, user_id=user_id, rule_id=rule_id, limit=limit)
    except ValueError as e:
        logger.info(
            "dev.rule_run.not_found",
            extra={
                "request_id": request_id,
                "user_id": str(user_id),
                "rule_id": str(rule_id),
                "error": str(e)[:200],
            },
        )
        raise HTTPException(status_code=404, detail="Rule not found") from e
    except SQLAlchemyError:
        logger.exception(
            "dev.rule_run.db_error",
            extra={"request_id": request_id, "user_id": str(user_id), "rule_id": str(rule_id)},
        )
        raise HTTPException(status_code=500, detail="db error") from None

    logger.info(
        "dev.rule_run.success",
        extra={
            "request_id": request_id,
            "user_id": str(user_id),
            "rule_id": str(rule_id),
            "fetched": summary.fetched,
            "listings_created": summary.listings_created,
            "snapshots_created": summary.snapshots_created,
            "matches_created": summary.matches_created,
        },
    )

    return {
        "rule_id": str(summary.rule_id),
        "fetched": summary.fetched,
        "listings_created": summary.listings_created,
        "snapshots_created": summary.snapshots_created,
        "matches_created": summary.matches_created,
    }
