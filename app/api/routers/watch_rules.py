from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_db
from app.core.logging import get_logger
from app.schemas.watch_rules import WatchRuleCreate, WatchRuleOut, WatchRuleUpdate
from app.services import watch_rules as service
from app.services.background import backfill_rule_matches_task

logger = get_logger(__name__)
router = APIRouter(prefix="/watch-rules", tags=["watch-rules"])


def _safe_sources(payload_query: dict | None) -> list[str] | None:
    if not isinstance(payload_query, dict):
        return None
    sources = payload_query.get("sources")
    if not isinstance(sources, list):
        return None
    return [str(s).strip().lower() for s in sources if str(s).strip()]


@router.post("", response_model=WatchRuleOut, status_code=201)
def create_rule(
    request: Request,
    payload: WatchRuleCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    request_id = getattr(request.state, "request_id", "-")
    logger.info(
        "watch_rules.create.call",
        extra={
            "request_id": request_id,
            "user_id": str(user_id),
            "poll_interval_seconds": payload.poll_interval_seconds,
            "sources": _safe_sources(payload.query),
        },
    )

    try:
        rule = service.create_watch_rule(
            db,
            user_id=user_id,
            name=payload.name,
            query=payload.query,
            poll_interval_seconds=payload.poll_interval_seconds,
        )
    except ValueError as e:
        # validation / domain error
        logger.info(
            "watch_rules.create.validation_error",
            extra={"request_id": request_id, "user_id": str(user_id), "error": str(e)[:500]},
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except SQLAlchemyError:
        logger.exception(
            "watch_rules.create.db_error",
            extra={"request_id": request_id, "user_id": str(user_id)},
        )
        raise HTTPException(status_code=500, detail="db error") from None

    # DEV: backfill recent listings so user sees matches immediately
    background_tasks.add_task(backfill_rule_matches_task, user_id, rule.id)

    logger.info(
        "watch_rules.create.success",
        extra={"request_id": request_id, "user_id": str(user_id), "rule_id": str(rule.id)},
    )
    return rule


@router.get("", response_model=list[WatchRuleOut])
def list_rules(
    request: Request,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    request_id = getattr(request.state, "request_id", "-")
    logger.debug(
        "watch_rules.list.call",
        extra={"request_id": request_id, "user_id": str(user_id), "limit": limit, "offset": offset},
    )

    try:
        rows = service.list_watch_rules(db, user_id=user_id, limit=limit, offset=offset)
    except SQLAlchemyError:
        logger.exception(
            "watch_rules.list.db_error",
            extra={"request_id": request_id, "user_id": str(user_id), "limit": limit, "offset": offset},
        )
        raise HTTPException(status_code=500, detail="db error") from None

    logger.info(
        "watch_rules.list.success",
        extra={
            "request_id": request_id,
            "user_id": str(user_id),
            "count": len(rows),
            "limit": limit,
            "offset": offset,
        },
    )
    return rows


@router.get("/{rule_id}", response_model=WatchRuleOut)
def get_rule(
    request: Request,
    rule_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    request_id = getattr(request.state, "request_id", "-")
    logger.debug(
        "watch_rules.get.call",
        extra={"request_id": request_id, "user_id": str(user_id), "rule_id": str(rule_id)},
    )

    try:
        rule = service.get_watch_rule(db, user_id=user_id, rule_id=rule_id)
    except HTTPException as e:
        # service currently raises 404 here
        if e.status_code == 404:
            logger.info(
                "watch_rules.get.not_found",
                extra={"request_id": request_id, "user_id": str(user_id), "rule_id": str(rule_id)},
            )
        raise
    except SQLAlchemyError:
        logger.exception(
            "watch_rules.get.db_error",
            extra={"request_id": request_id, "user_id": str(user_id), "rule_id": str(rule_id)},
        )
        raise HTTPException(status_code=500, detail="db error") from None

    logger.info(
        "watch_rules.get.success",
        extra={"request_id": request_id, "user_id": str(user_id), "rule_id": str(rule_id)},
    )
    return rule


@router.patch("/{rule_id}", response_model=WatchRuleOut)
def patch_rule(
    request: Request,
    rule_id: UUID,
    payload: WatchRuleUpdate,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    request_id = getattr(request.state, "request_id", "-")
    logger.info(
        "watch_rules.patch.call",
        extra={
            "request_id": request_id,
            "user_id": str(user_id),
            "rule_id": str(rule_id),
            "has_name": payload.name is not None,
            "has_query": payload.query is not None,
            "has_is_active": payload.is_active is not None,
            "has_poll_interval": payload.poll_interval_seconds is not None,
            "sources": _safe_sources(payload.query) if payload.query else None,
        },
    )

    try:
        updated = service.update_watch_rule(
            db,
            user_id=user_id,
            rule_id=rule_id,
            name=payload.name,
            query=payload.query,
            is_active=payload.is_active,
            poll_interval_seconds=payload.poll_interval_seconds,
        )
    except ValueError as e:
        # your service raises ValueError for "Rule not found for user" and validation
        msg = str(e)
        status = 404 if "not found" in msg.lower() else 400
        event = "watch_rules.patch.not_found" if status == 404 else "watch_rules.patch.validation_error"
        logger.info(
            event,
            extra={
                "request_id": request_id,
                "user_id": str(user_id),
                "rule_id": str(rule_id),
                "error": msg[:500],
            },
        )
        raise HTTPException(status_code=status, detail=msg) from e
    except SQLAlchemyError:
        logger.exception(
            "watch_rules.patch.db_error",
            extra={"request_id": request_id, "user_id": str(user_id), "rule_id": str(rule_id)},
        )
        raise HTTPException(status_code=500, detail="db error") from None

    logger.info(
        "watch_rules.patch.success",
        extra={"request_id": request_id, "user_id": str(user_id), "rule_id": str(rule_id)},
    )
    return updated


@router.delete("/{rule_id}", response_model=WatchRuleOut)
def disable_rule(
    request: Request,
    rule_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    request_id = getattr(request.state, "request_id", "-")
    logger.info(
        "watch_rules.disable.call",
        extra={"request_id": request_id, "user_id": str(user_id), "rule_id": str(rule_id)},
    )

    try:
        updated = service.disable_watch_rule(db, user_id=user_id, rule_id=rule_id)
    except ValueError as e:
        msg = str(e)
        status = 404 if "not found" in msg.lower() else 400
        event = "watch_rules.disable.not_found" if status == 404 else "watch_rules.disable.validation_error"
        logger.info(
            event,
            extra={
                "request_id": request_id,
                "user_id": str(user_id),
                "rule_id": str(rule_id),
                "error": msg[:500],
            },
        )
        raise HTTPException(status_code=status, detail=msg) from e
    except SQLAlchemyError:
        logger.exception(
            "watch_rules.disable.db_error",
            extra={"request_id": request_id, "user_id": str(user_id), "rule_id": str(rule_id)},
        )
        raise HTTPException(status_code=500, detail="db error") from None

    logger.info(
        "watch_rules.disable.success",
        extra={"request_id": request_id, "user_id": str(user_id), "rule_id": str(rule_id)},
    )
    return updated
